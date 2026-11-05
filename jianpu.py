#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jianpu.py — MP3/MP4 → 每小节人声简谱（全本地、全开源流水线）

流程（每个环节均为开源工具，全程不联网调用外部服务）:
  1) ffmpeg       任意音视频(mp3/mp4/wav/flac...) → 统一 44.1kHz WAV
  2) demucs       混音 → 纯人声/伴奏 两轨分离 (Facebook MIT)
  3) basic-pitch  纯人声 → 音符事件(时间+音高) + MIDI (Spotify Apache-2.0)
  4) librosa      原始混音 → 节拍网格；音符音高直方图 → 调号(Krumhansl-Schmuckler)
  5) 简谱映射      音高 → 1234567 (含 #4 等变音)，按 [小节][拍] 分组输出
  6) 和弦检测      伴奏 chroma → 每小节和弦(模板匹配+调性先验)，txt/html/pdf 输出
                   和弦名 + 吉他指法图; PDF 简谱下方附逐音符歌词(同 jianpu.html)

用法示例:
  python jianpu.py song.mp4 -o out                 # 全自动
  python jianpu.py vocal.wav --no-separate --bpm 90 --key C
  python jianpu.py song.mp3 --bar-shift 1          # 小节线整体后移一拍(弱起)
"""

import argparse
import bisect
import csv
import math
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# 大调音阶: 半音差 → 简谱数字
MAJOR_DIGITS = {0: '1', 2: '2', 4: '3', 5: '4', 7: '5', 9: '6', 11: '7'}
# 变音(黑键) → 升号记法
SHARP_DIGITS = {1: '#1', 3: '#2', 6: '#4', 8: '#5', 10: '#6'}

# Krumhansl-Schmuckler 调性模板（十二个半音上的调性权重）
KS_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KS_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def log(msg):
    print(f"[jianpu] {msg}", flush=True)


# 中文 Windows 控制台(GBK)兜底: 无法编码的字符替换为'?'而不是崩溃
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except Exception:
        pass


# ---------------------------------------------------------------- 阶段1: 音频抽取
def extract_wav(input_path: Path, out_wav: Path) -> None:
    """ffmpeg 把任意输入统一转成 44.1kHz 立体声 wav（demucs 原生采样率）"""
    if not shutil.which('ffmpeg'):
        sys.exit("错误: 未找到 ffmpeg。请安装后重试，例如: winget install Gyan.FFmpeg")
    cmd = ['ffmpeg', '-y', '-i', str(input_path), '-vn', '-ac', '2', '-ar', '44100', str(out_wav)]
    # 注意: text=True 不指定 encoding 时 Windows 会用 GBK 解码 ffmpeg 的 UTF-8 输出,
    # 遇到中文歌名即抛 UnicodeDecodeError, 必须显式 encoding='utf-8'
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if r.returncode != 0:
        sys.exit(f"错误: ffmpeg 转码失败:\n{(r.stderr or '')[-1500:]}")


# ---------------------------------------------------------------- 阶段2: 人声分离
def separate_vocals(mix_wav: Path, sep_dir: Path, model: str) -> Path:
    """demucs --two-stems=vocals，返回人声 wav 路径"""
    def demucs_cmd():
        # 优先用 venv 里的 console script，退回 -c 直调入口
        exe = Path(sys.executable).with_name('demucs.exe' if os.name == 'nt' else 'demucs')
        if exe.exists():
            return [str(exe)]
        w = shutil.which('demucs')
        if w:
            return [w]
        return [sys.executable, '-c', 'import sys; from demucs.separate import main; main()']

    cmd = demucs_cmd() + ['--two-stems', 'vocals', '-n', model, '-o', str(sep_dir), str(mix_wav)]
    log(f"人声分离: {' '.join(cmd[:2])} ... (首次运行需下载模型 ~80MB)")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit("错误: demucs 分离失败。可加 --no-separate 跳过（适合清唱/已分离人声）")
    vocals = sorted(sep_dir.glob(f'*/**/vocals.wav')) or sorted(sep_dir.glob('**/vocals.wav'))
    if not vocals:
        sys.exit(f"错误: 未找到 demucs 输出，请检查目录 {sep_dir}")
    return vocals[0]


# ---------------------------------------------------------------- 阶段3: 音符转写
def compute_onset_curve(vocal_wav: Path):
    """librosa 起音强度包络 → (env, times)，用于切开"同音高连唱多个字"的长音符"""
    import librosa
    import numpy as np
    y, sr = librosa.load(str(vocal_wav), sr=22050, mono=True)
    hop = 256
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    times = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=hop)
    return env, times


def env_strength(env, times, t0: float, t1: float) -> float:
    """[t0,t1] 时间窗内的起音强度峰值"""
    import numpy as np
    m = (times >= t0) & (times <= t1)
    return float(env[m].max()) if m.any() else 0.0


def merge_tiny_and_filter(notes: list, min_len: float) -> list:
    """过滤过短音符；仅合并相互重叠的同音碎片（转写器的拆分伪影才会重叠,
    SOME 等引擎无缝衔接的同音换字是独立音符, 不可合并）"""
    notes = sorted(notes, key=lambda n: (n['start'], n['pitch']))
    merged = []
    for n in notes:
        prev = merged[-1] if merged else None
        same_cut = (prev and prev['pitch'] == n['pitch']
                    and n['start'] < prev['end'] - 0.005)
        if same_cut:
            prev['end'] = max(prev['end'], n['end'])
            continue
        if n['end'] - n['start'] >= min_len:
            merged.append(n)
        elif prev and prev['pitch'] == n['pitch'] and n['start'] < prev['end'] - 0.005:
            prev['end'] = max(prev['end'], n['end'])  # 碎片并入前同音
    return merged


def monophonic_cleanup(notes: list) -> list:
    """单声部清谱: 时间上大幅重叠的两个音保留较强者（过滤谐波幽灵/重影）"""
    import numpy as _np  # noqa: F401  (保持依赖面不变)
    mono = []
    for n in sorted(notes, key=lambda x: (x['start'], -x['amp'])):
        if mono:
            p = mono[-1]
            ov = min(p['end'], n['end']) - n['start']
            if ov > 0.5 * min(p['end'] - p['start'], n['end'] - n['start']):
                if n['amp'] > p['amp']:
                    mono[-1] = n
                continue
        mono.append(n)
    return sorted(mono, key=lambda x: x['start'])


def find_some_ckpt() -> Path:
    for pat in ('pretrained/*.ckpt', 'pretrained/**/*.ckpt'):
        cks = sorted((VENDOR_DIR / 'SOME').glob(pat))
        if cks:
            return cks[0]
    return None


def transcribe_notes_some(vocal_wav: Path, work_dir: Path):
    """SOME (Singing-Oriented MIDI Extractor, openvpi) → 歌声专用音符转写。
    调用 vendor/SOME/infer.py 产出 MIDI 再解析为统一 notes 结构"""
    ckpt = find_some_ckpt()
    if ckpt is None:
        raise FileNotFoundError('SOME 预训练模型未下载 (vendor/SOME/pretrained/)')
    out_mid = work_dir / 'some.mid'
    cmd = [sys.executable, str(VENDOR_DIR / 'SOME' / 'infer.py'),
           '--model', str(ckpt), '--wav', str(vocal_wav), '--midi', str(out_mid)]
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', cwd=str(VENDOR_DIR / 'SOME'), env=env)
    if r.returncode != 0 or not out_mid.exists():
        raise RuntimeError(f'SOME 推理失败:\n{(r.stderr or r.stdout or "")[-800:]}')
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(out_mid))
    notes = [dict(start=float(n.start), end=float(n.end), pitch=int(n.pitch),
                  amp=float(n.velocity) / 127.0)
             for inst in pm.instruments for n in inst.notes]
    return notes, out_mid


def transcribe_notes(vocal_wav: Path, onset_th: float, frame_th: float,
                     min_len: float, beat_len: float) -> list:
    """basic-pitch → [{'start','end','pitch','amp'}, ...]（已过滤/合并/按起音切分）"""
    from basic_pitch.inference import predict
    log(f"音符转写: basic-pitch (onset={onset_th}, frame={frame_th})")
    out = predict(str(vocal_wav), onset_threshold=onset_th, frame_threshold=frame_th)

    # 兼容不同版本返回结构
    note_events = out.note_events if hasattr(out, 'note_events') else (
        out[2] if isinstance(out, tuple) else out)
    if hasattr(note_events, 'notes'):
        raw = note_events.notes
    elif isinstance(note_events, dict):
        raw = note_events.get('note_events') or note_events.get('notes')
    else:
        raw = note_events

    notes = [dict(start=float(ev[0]), end=float(ev[1]),
                  pitch=int(round(float(ev[2]))), amp=float(ev[3]))
             for ev in raw]
    merged = monophonic_cleanup(merge_tiny_and_filter(notes, min_len))

    # basic-pitch 常把"同音高连唱多个字"并成一个长音符 → 用音频起音峰切开。
    # 三重防误切: ①音符时长 ≥0.95 拍才允许切; ②切点强度 ≥ 自身起音的 55%;
    #            ③切点间距 ≥0.5 拍, 且每音符最多切 3 刀
    try:
        import librosa
        env, times = compute_onset_curve(vocal_wav)
        peak_idx = librosa.util.peak_pick(
            env, pre_max=8, post_max=8, pre_avg=16, post_avg=16,
            delta=max(0.5, 0.05 * float(env.max())), wait=8)
        cand_t = [float(times[i]) for i in peak_idx]
    except Exception as e:
        log(f"警告: 起音分析失败({e})，跳过长音符切分")
        cand_t, env, times = [], None, None

    if cand_t:
        import bisect as _b
        split_notes = []
        for n in merged:
            dur = n['end'] - n['start']
            if dur < max(0.35, 0.95 * beat_len):
                split_notes.append(n)
                continue
            attack = env_strength(env, times, n['start'], n['start'] + 0.08) or 1e-6
            lo = _b.bisect_right(cand_t, n['start'] + 0.15)
            hi = _b.bisect_left(cand_t, n['end'] - 0.12)
            cuts = [n['start']]
            min_gap = max(0.15, 0.5 * beat_len)
            for t in cand_t[lo:hi]:
                if (env_strength(env, times, t - 0.03, t + 0.03) > 0.75 * attack
                        and t - cuts[-1] >= min_gap and len(cuts) <= 3):
                    cuts.append(t)
            cuts.append(n['end'])
            if len(cuts) == 2:
                split_notes.append(n)
                continue
            for a, b in zip(cuts[:-1], cuts[1:]):
                if b - a >= min_len:
                    split_notes.append(dict(start=a, end=b, pitch=n['pitch'], amp=n['amp']))
        merged = split_notes
    merged.sort(key=lambda n: n['start'])
    log(f"        共 {len(merged)} 个音符")
    return merged, out


def save_midi(out, midi_path: Path):
    try:
        midi = out.midi_data if hasattr(out, 'midi_data') else out[1]
        midi.write(str(midi_path))
    except Exception as e:  # MIDI 仅是附属产物，失败不影响简谱
        log(f"警告: MIDI 保存失败({e})，跳过")


# ---------------------------------------------------------------- 阶段4a: 调号
def estimate_key(notes: list):
    """按时长×力度×节拍位置加权音级直方图 + KS 模板匹配 → (tonic_pc, 'major'/'minor', 相关度)
    n['w']: 强拍权重(主音/属音倾向落在小节重拍上, 是调号最可靠的线索)"""
    if not notes:
        return 0, 'major', 0.0
    amps = sorted(n['amp'] for n in notes)
    med = amps[len(amps) // 2] or 1e-6
    hist = [0.0] * 12
    for n in notes:
        if n['amp'] < 0.5 * med:      # 忽略过弱音符(多为分离残响)
            continue
        hist[n['pitch'] % 12] += (n['end'] - n['start']) * (0.5 + n['amp']) * n.get('w', 1.0)

    def corr(profile, shift):
        h = hist[shift:] + hist[:shift]
        mh, mp = sum(h) / 12, sum(profile) / 12
        num = sum((h[i] - mh) * (profile[i] - mp) for i in range(12))
        den = math.sqrt(sum((h[i] - mh) ** 2 for i in range(12))
                        * sum((profile[i] - mp) ** 2 for i in range(12))) or 1e-9
        return num / den

    best = max(((corr(KS_MAJOR, s), s, 'major') for s in range(12)))
    best_min = max(((corr(KS_MINOR, s), s, 'minor') for s in range(12)))
    c, tonic, mode = best if best[0] >= best_min[0] else best_min
    return tonic, mode, c


def parse_key_arg(s: str):
    """'C' / 'Am' / 'F#' / '1=D' → (tonic_pc, mode)"""
    s = s.strip().replace('1=', '')
    if s.lower().endswith('m') and len(s) > 1:
        return NOTE_NAMES.index(s[:-1].upper()), 'minor'
    return NOTE_NAMES.index(s.upper()), 'major'


# ---------------------------------------------------------------- 阶段4b: 节拍
VENDOR_DIR = Path(__file__).resolve().parent / 'vendor'


def _resolve_beat_model(name: str) -> str:
    """--beat-model best: final0 已缓存则用 final0(更准), 否则 small0(8MB 首跑自动下载)"""
    if name != 'best':
        return name
    hub = Path.home() / '.cache' / 'torch' / 'hub' / 'checkpoints' / 'beat_this-final0.ckpt'
    return 'final0' if hub.exists() and hub.stat().st_size > 81_000_000 else 'small0'


def track_beats_beat_this(mix_wav: Path, model: str = 'final0'):
    """beat_this (ISMIR 2024) → (bpm, 拍时刻, downbeat时刻)。
    downbeat 即小节线位置, 精度显著高于 librosa 均匀网格。失败时抛异常由调用方回退"""
    import numpy as np
    from beat_this.inference import File2Beats
    f2b = File2Beats(checkpoint_path=model, device='cpu', dbn=False)
    beats, downbeats = f2b(str(mix_wav))
    beats = sorted(float(b) for b in beats)
    downbeats = sorted(float(d) for d in downbeats)
    if len(beats) < 4 or not downbeats:
        raise RuntimeError('beat_this 输出拍点不足')
    import numpy as _np
    bpm = 60.0 / float(_np.median(_np.diff(beats)))
    return float(bpm), beats, downbeats


def infer_beats_per_measure(downbeats: list, beat_len: float, default: int = 4) -> int:
    """downbeat 间距 ÷ 拍长 → 自动拍号(每小节拍数)。不依赖拍点计数, 倍速歧义下也正确"""
    import numpy as np
    if len(downbeats) < 2 or beat_len <= 0:
        return default
    bar_med = float(np.median(np.diff(downbeats)))
    n = int(round(bar_med / beat_len))
    return n if 2 <= n <= 12 else default


def build_bar_grid_dbt(downbeats: list, duration: float, bar_len: float):
    """以 beat_this 的 downbeat 为小节线构建网格(非均匀也支持);
    首个 downbeat 之前最多补 4 个"前奏"虚拟小节(编号0), 最后一个之后按 bar_len 外推"""
    bars = []
    lead, leads = downbeats[0], []
    while lead - bar_len > -bar_len and len(leads) < 4:
        lead -= bar_len
        leads.append((0, lead))
    leads.reverse()
    n, t = 1, downbeats[0]
    while t < duration + bar_len:
        bars.append((n, t))
        n += 1
        t = downbeats[n - 1] if n - 1 < len(downbeats) else t + bar_len
    return leads + bars


def track_beats(mix_wav: Path, bpm: float = None):
    """librosa 节拍追踪 → (实际bpm, 拍时刻列表, 总时长)"""
    import librosa
    import soundfile as sf
    y, sr = librosa.load(str(mix_wav), sr=22050, mono=True)
    duration = float(sf.info(str(mix_wav)).duration)
    kw = dict(units='time', trim=False)
    if bpm:
        kw['bpm'] = bpm
    try:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, **kw)
    except TypeError:  # 旧版 librosa 无 bpm 覆盖参数
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time', trim=False)
    tempo = float(tempo.item() if hasattr(tempo, 'item') else tempo)
    if len(beats) < 2:
        tempo = bpm or 90.0
        beats = []
        log(f"警告: 节拍追踪失败，使用 {tempo:.0f} BPM 均匀网格")
    return tempo, [float(b) for b in beats], duration


def build_bar_grid(beats: list, duration: float, beats_per_bar: int,
                   bar_shift: int, bpm: float):
    """拍网格 → 小节网格 [(小节号, 起始时间), ...]；小节号 0 表示前奏不完整小节"""
    import numpy as np
    if len(beats) >= 2:
        beat_len = float(np.median(np.diff(beats)))
        first_beat = beats[0]
    else:
        beat_len = 60.0 / bpm
        first_beat = 0.0
    if bpm:
        beat_len = 60.0 / bpm
    bar_len = beat_len * beats_per_bar
    first_bar = first_beat + bar_shift * beat_len

    bars = []
    t, idx = first_bar, 1
    while t < duration + bar_len:
        bars.append((idx, t))
        t += bar_len
        idx += 1
    # 小节线之前的音符归入 "前奏"(小节号0)；最多向前铺 4 个虚拟小节，再早就并入第0小节
    lead = first_bar
    for _ in range(4):
        lead -= bar_len
        if lead < -bar_len:
            break
        bars.insert(0, (0, lead))
    bars = [(n, t) for (n, t) in bars if t < duration + bar_len and (t >= -bar_len)]
    return bars, beat_len


# ---------------------------------------------------------------- 阶段4c: 和弦检测
# 和弦模板: 显示后缀 → {相对根音半音差: 度数权重}。
# 权重(根音1.0 > 五音0.75 > 三音0.6 > 七音0.45)使七和弦只在七音真实存在时才胜出,
# 否则人声旋律的经过音(2nd/4th/6th)会把三和弦误判成七和弦
CHORD_TEMPLATES = {
    '':     {0: 1.0, 4: 0.6, 7: 0.75},          # 大三和弦 C
    'm':    {0: 1.0, 3: 0.6, 7: 0.75},          # 小三和弦 Cm
    '7':    {0: 1.0, 4: 0.6, 7: 0.75, 10: 0.45},  # 属七 C7
    'm7':   {0: 1.0, 3: 0.6, 7: 0.75, 10: 0.45},  # 小七 Cm7
    'maj7': {0: 1.0, 4: 0.6, 7: 0.75, 11: 0.45},  # 大七 Cmaj7
}
# 七和弦 Occam 惩罚: 泛音/邻小节谐波泄漏常把三和弦误判成七和弦,
# 只有七音证据强于惩罚值时才保留七和弦(真实歌曲调得: 0.05~0.06)
CHORD_SUFFIX_PENALTY = {'': 0.0, 'm': 0.0, '7': 0.05, 'm7': 0.05, 'maj7': 0.06}
# 调内顺阶和弦根音(相对调主音半音差): 只有这些根音吃调性先验加分
DIATONIC_ROOTS = {
    'major': {0, 2, 4, 5, 7, 9},   # I ii iii IV V vi
    'minor': {0, 3, 5, 7, 8, 10},  # i III iv v VI VII (自然小调)
}


def detect_chords(audio_wav: Path, bars: list, beat_len: float, beats_per_bar: int,
                  key_tonic: int, key_mode: str) -> dict:
    """伴奏(优先)/全混音 + 小节网格 → {小节号: 和弦名 or None(N.C.)}。
    每小节: chroma_cqt(fmin=C2 排除底鼓) 中位数 → 12根音×5性质 加权模板余弦
    + 低音区根音加分(贝斯/垫音最低音≈根音) + 调性先验;
    能量过低的窗(前奏/尾奏静音) → None。纯 librosa+numpy"""
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_wav), sr=22050, mono=True)
    dur = len(y) / sr
    hop = 512
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop, fmin=65.41)
    # 低音根音线索: 每帧 C2..C4 中"最低的显著bin"的音级(贝斯/垫音最低音多为根音,
    # 基频低于C2时其二次谐波落在窗内且同音级) —— 纠"最响音≠根音"的误判
    C = np.abs(librosa.cqt(y=y, sr=sr, hop_length=hop, fmin=65.41,
                           n_bins=24, bins_per_octave=12))
    sig = C >= 0.25 * C.max(axis=0, keepdims=True)
    pc_frame = np.where(sig.any(axis=0), sig.argmax(axis=0) % 12, -1)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop)
    rms_med = float(np.median(rms)) or 1e-9

    diatonic = DIATONIC_ROOTS.get(key_mode, DIATONIC_ROOTS['major'])
    out = {}
    for i, (m, t0) in enumerate(bars):
        t1 = bars[i + 1][1] if i + 1 < len(bars) else t0 + beats_per_bar * beat_len
        t0, t1 = max(0.0, t0), min(dur, t1)
        mask = (times >= t0) & (times < t1)
        if not mask.any() or t1 - t0 < 0.2 or float(np.median(rms[mask])) < 0.08 * rms_med:
            out[m] = None   # 静音/超短窗 → N.C.
            continue
        ch = np.median(chroma[:, mask], axis=1)
        ch = ch / (float(np.max(ch)) or 1e-9)
        ch_norm = math.sqrt(float(ch @ ch)) or 1e-9
        sel = pc_frame[mask[:len(pc_frame)]]
        hist = np.bincount(sel[sel >= 0], minlength=12)
        bmax = int(hist.max())
        best, best_v = ('', -9.9)
        for root in range(12):
            bass_bonus = 0.2 * hist[root] / bmax if bmax else 0.0
            for suffix, ivs in CHORD_TEMPLATES.items():
                t = np.zeros(12)
                for iv, wgt in ivs.items():
                    t[(root + iv) % 12] = wgt
                v = float(ch @ t) / (math.sqrt(float(t @ t)) * ch_norm)  # 余弦相关
                v += bass_bonus - CHORD_SUFFIX_PENALTY[suffix]
                if (root - key_tonic) % 12 in diatonic:
                    v += 0.06                                # 调性先验: 只破平局
                if v > best_v:
                    best, best_v = (NOTE_NAMES[root] + suffix), v
        out[m] = best
    return out


# ---------------------------------------------------------------- 阶段5: 简谱映射
def octave_offset(pitch: int, tonic_pc: int, ref_midi: int) -> int:
    """相对八度偏移: 以 ref_midi(人声 median) 下方最近的“1”为基准"""
    ref = ref_midi - ((ref_midi - tonic_pc) % 12)
    return (pitch - ref) // 12


def pitch_to_jianpu(pitch: int, tonic_pc: int, show_octave: bool, ref_midi: int) -> str:
    d = (pitch - tonic_pc) % 12
    digit = MAJOR_DIGITS.get(d) or SHARP_DIGITS[d]
    if not show_octave:
        return digit
    rel = octave_offset(pitch, tonic_pc, ref_midi)
    if rel > 0:
        return digit + '^' * rel
    if rel < 0:
        return digit + '_' * (-rel)
    return digit


def locate_note(start: float, bars: list, beat_len: float, beats_per_bar: int):
    """音符 → (小节号, 拍序)。
    量化规则: 距整数拍±0.15内吸附到该拍(消除起音抖动/跨界), 其余向下取整
    (八分音符在0.5拍处、十六分在0.25/0.75拍处, 都归入所在的这一拍)"""
    starts = [t for _, t in bars]
    i = bisect.bisect_right(starts, start + 1e-6) - 1
    if i < 0:
        m, bar_t = 0, starts[0] - beat_len * beats_per_bar
    else:
        m, bar_t = bars[i]
    pos = (start - bar_t) / beat_len
    near = round(pos)
    pos = int(near) if abs(pos - near) <= 0.15 else int(math.floor(pos))
    if pos >= beats_per_bar and i + 1 < len(bars):   # 实际属于下一小节头部
        m, bar_t = bars[i + 1]
        pos = 0
    elif pos < 0 and i > 0:                          # 实际属于上一小节尾部
        m, bar_t = bars[i - 1]
        pos = beats_per_bar - 1
    bi = max(0, min(beats_per_bar - 1, pos))
    return m, bi


def build_measure_cells(notes: list, bars: list, beat_len: float, beats_per_bar: int,
                        tonic_pc: int, ref_midi: int):
    """音符 → [(小节号, [拍格×beats_per_bar])]
    拍格: None=休止(0) / 'hold'=延音(—) / [音符dict{pitch,dur(拍),oct}]
    补齐首尾之间的空白小节(间奏)保持网格连续; 延音: 时长≥1.5拍则占后续拍格"""
    placed = {}
    for n in sorted(notes, key=lambda x: x['start']):
        m, bi = locate_note(n['start'], bars, beat_len, beats_per_bar)
        dur_beats = (n['end'] - n['start']) / beat_len
        placed.setdefault(m, {}).setdefault(bi, []).append(
            dict(pitch=n['pitch'], dur=dur_beats,
                 oct=octave_offset(n['pitch'], tonic_pc, ref_midi),
                 word=n.get('word', '')))
    # 延音填充: 该拍最长音符按 round(时长) 占据后续拍格(不覆盖已有音符, 不跨小节)
    for m in list(placed):
        for bi in list(placed[m]):
            entries = placed[m][bi]
            if entries == 'hold':
                continue
            holds = max(0, max(int(round(e['dur'])) for e in entries) - 1)
            for k in range(1, holds + 1):
                if bi + k < beats_per_bar and bi + k not in placed[m]:
                    placed[m][bi + k] = 'hold'
    if not placed:
        return []
    return [(m, [placed.get(m, {}).get(bi) for bi in range(beats_per_bar)])
            for m in range(min(placed), max(placed) + 1)]


def cell_text(cell, tonic_pc: int, show_octave: bool) -> str:
    """拍格 → 文本: 休止0 / 延音— / 音符连写(拍内多音如 33)"""
    if cell is None:
        return '0'
    if cell == 'hold':
        return '—'
    out = ''
    for e in cell:
        d = (e['pitch'] - tonic_pc) % 12
        digit = MAJOR_DIGITS.get(d) or SHARP_DIGITS[d]
        if show_octave and e['oct'] > 0:
            digit += '^' * e['oct']
        elif show_octave and e['oct'] < 0:
            digit += '_' * (-e['oct'])
        out += digit
    return out


# ------------------------------------------------- 吉他指法表(和弦图: HTML SVG / PDF 同源)
# 开放把位常用和弦: 品位低→高(EADGBE), -1=闷音(x), 0=空弦(o)
GUITAR_OPEN_CHORDS = {
    'C': (-1, 3, 2, 0, 1, 0),      'Cmaj7': (-1, 3, 2, 0, 0, 0),
    'C7': (-1, 3, 2, 3, 1, 0),
    'D': (-1, -1, 0, 2, 3, 2),     'Dm': (-1, -1, 0, 2, 3, 1),
    'D7': (-1, -1, 0, 2, 1, 2),    'Dm7': (-1, -1, 0, 2, 1, 1),
    'E': (0, 2, 2, 1, 0, 0),       'Em': (0, 2, 2, 0, 0, 0),
    'E7': (0, 2, 0, 1, 0, 0),      'Em7': (0, 2, 0, 0, 0, 0),
    'Emaj7': (0, 2, 1, 1, 0, 0),
    'G': (3, 2, 0, 0, 0, 3),       'G7': (3, 2, 0, 0, 0, 1),
    'A': (-1, 0, 2, 2, 2, 0),      'Am': (-1, 0, 2, 2, 1, 0),
    'A7': (-1, 0, 2, 0, 2, 0),     'Am7': (-1, 0, 2, 0, 1, 0),
    'Amaj7': (-1, 0, 2, 1, 2, 0),  'B7': (-1, 2, 1, 2, 0, 2),
}
# 横按形状(品位相对横按位置的偏移): E 型根音在 6 弦 / A 型根音在 5 弦
_BARRE_E = {'': (0, 2, 2, 1, 0, 0), 'm': (0, 2, 2, 0, 0, 0), '7': (0, 2, 0, 1, 0, 0),
            'm7': (0, 2, 0, 0, 0, 0), 'maj7': (0, 2, 1, 1, 0, 0)}
_BARRE_A = {'': (-1, 0, 2, 2, 2, 0), 'm': (-1, 0, 2, 2, 1, 0), '7': (-1, 0, 2, 0, 2, 0),
            'm7': (-1, 0, 2, 0, 1, 0), 'maj7': (-1, 0, 2, 1, 2, 0)}


def parse_chord_name(name: str):
    """'C' / 'F#' / 'Bbm' → (root_pc, 后缀)；无法解析返回 None"""
    for pc, n in enumerate(NOTE_NAMES):
        if name.startswith(n) and name[len(n):] in CHORD_TEMPLATES:
            return pc, name[len(n):]
    return None


def guitar_fingering(name: str):
    """和弦名 → (品位低→高 tuple, 显示基准品) 或 None(未知和弦)。
    开放把位优先, 其余按根音离空把更近的一侧生成 E 型/A 型横按"""
    if name in GUITAR_OPEN_CHORDS:
        frets = GUITAR_OPEN_CHORDS[name]
    else:
        parsed = parse_chord_name(name)
        if not parsed:
            return None
        pc, suffix = parsed
        f_e, f_a = (pc - 4) % 12, (pc - 9) % 12   # 6 弦/5 弦上的把位
        if f_a and (not f_e or f_a < f_e):
            base, shape = f_a, _BARRE_A[suffix]
        else:
            base, shape = max(f_e, 1), _BARRE_E[suffix]
        frets = tuple(-1 if f < 0 else f + base for f in shape)
    played = [f for f in frets if f > 0]
    base_fret = min(played) if played and max(played) > 5 else 1
    return frets, base_fret


def chord_svg(name: str) -> str:
    """和弦名 → 内联 SVG 指法图(六弦×5品, 圆点/空弦/闷音标记, 把位号)"""
    fr = guitar_fingering(name)
    if not fr:
        return ''
    frets, base = fr
    L, T, W_STR, H_FRET, M = 6, 15, 10, 10, 12   # 左边距/网格顶/弦距/品高/标记行高
    parts = [f'<svg class="fret" viewBox="0 0 64 78" width="60" height="73" '
             f'xmlns="http://www.w3.org/2000/svg">',
             '<g stroke="#444" stroke-width="1" stroke-linecap="round">']
    if base == 1:   # 上弦枕加粗
        parts.append(f'<rect x="{L - 1}" y="{T - 2.5}" width="{W_STR * 5 + 2}" height="3" fill="#444"/>')
    for i in range(6):   # 六根竖线(低音弦在左)
        x = L + i * W_STR
        parts.append(f'<line x1="{x}" y1="{T}" x2="{x}" y2="{T + H_FRET * 5}"/>')
    for j in range(6):   # 六条横线(5 品格)
        y = T + j * H_FRET
        parts.append(f'<line x1="{L}" y1="{y}" x2="{L + W_STR * 5}" y2="{y}"/>')
    if base > 1:     # 把位号
        parts.append(f'<text x="0" y="{T + 9}" font-size="8" fill="#666">{base}fr</text>')
    for i, f in enumerate(frets):
        x = L + i * W_STR
        if f < 0:
            parts.append(f'<text x="{x - 3}" y="{M - 1}" font-size="8" fill="#888">×</text>')
        elif f == 0:
            parts.append(f'<circle cx="{x}" cy="{M - 4}" r="2.6" fill="none" stroke="#666"/>')
        else:
            cy = T + (f - base + 0.5) * H_FRET
            parts.append(f'<circle cx="{x}" cy="{cy:.1f}" r="3.6" fill="#333"/>')
    parts.append('</g></svg>')
    return ''.join(parts)


def render_score_rows(measures: list, tonic_pc: int, show_octave: bool, per_line: int = 4,
                      chords: dict = None):
    """→ (行列表, 整曲单行)。每行 per_line 个小节, 行首为该行第一小节编号;
    chords={小节号: 和弦名} 时每行上方加一行和弦名(按小节宽度对齐, N.C.留空)"""
    texts = [(m, ' '.join(cell_text(c, tonic_pc, show_octave) for c in cells))
             for m, cells in measures]
    chord_map = chords or {}
    rows = []
    for i in range(0, len(texts), per_line):
        chunk = texts[i:i + per_line]
        rows.append(f"{chunk[0][0]:>3} | " + ' | '.join(t for _, t in chunk))
        if chord_map:
            cells = [(chord_map.get(m) or '').ljust(len(t) if j < len(chunk) - 1 else 0)
                     for j, (m, t) in enumerate(chunk)]
            if any(c.strip() for c in cells):
                rows.append(' ' * 5 + '| ' + ' | '.join(c for c in cells).rstrip())
    one_line = ' | '.join(t for _, t in texts)
    return rows, one_line


def write_score_html(path: Path, title: str, key_str: str, bpm: float,
                     beats_per_bar: int, measures: list, tonic_pc: int,
                     per_line: int = 4, chords: dict = None) -> None:
    """生成静态网页乐谱 jianpu.html: 每行4小节、行首编号、小节竖线、
    八度点(上高下低)、八分/十六分音符下划线、延音—、休止0, 可直接打印;
    chords={小节号: 和弦名} 时每小节上方加和弦名+吉他指法图(SVG)"""
    import html as _html

    def note_span(e):
        d = (e['pitch'] - tonic_pc) % 12
        digit = MAJOR_DIGITS.get(d) or SHARP_DIGITS[d]
        ul = 0 if e['dur'] >= 0.75 else (1 if e['dur'] >= 0.35 else 2)
        cls = f"n u{ul}" if ul else "n"
        dots = ''
        for i in range(min(e['oct'], 3)):        # 高音点(上方)
            dots += f'<i class="dot hi" style="top:{-3 - 5 * i}px"></i>'
        for i in range(min(-e['oct'], 3)):       # 低音点(下方)
            dots += f'<i class="dot lo" style="bottom:{-4 - 5 * i}px"></i>'
        lyric = (f'<b class="lyr">{_html.escape(e.get("word") or "")}</b>'
                 if e.get('word') else '')
        return f'<span class="{cls}">{dots}{digit}{lyric}</span>'

    def measure_html(cells, chord):
        parts = []
        for c in cells:
            if c is None:
                parts.append('<span class="rest">0</span>')
            elif c == 'hold':
                parts.append('<span class="hold">—</span>')
            else:
                parts.append(''.join(note_span(e) for e in c))
        beats = '<div class="beat">' + '</div><div class="beat">'.join(parts) + '</div>'
        head = ''
        if chord:
            svg = chord_svg(chord)
            head = (f'<div class="chord"><div class="cname">{_html.escape(chord)}</div>'
                    + (svg or '') + '</div>')
        elif chords:                       # 有和弦的小节行里保持对齐的占位
            head = '<div class="chord"></div>'
        return f'{head}<div class="beats">{beats}</div>'

    chord_map = chords or {}
    rows_html = []
    for i in range(0, len(measures), per_line):
        chunk = measures[i:i + per_line]
        ms = ''.join(f'<div class="m">{measure_html(cells, chord_map.get(m))}</div>'
                     for m, cells in chunk)
        rows_html.append(f'<div class="row"><span class="mno">{chunk[0][0]}</span>{ms}</div>')

    doc = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>{_html.escape(title)} — 简谱</title>
<style>
 body {{ font-family: "KaiTi","STKaiti","SimSun",serif; background:#fff; color:#111;
        max-width: 920px; margin: 24px auto; padding: 0 16px; }}
 h1  {{ font-size: 20px; text-align: center; margin: 6px 0 2px; }}
 .meta {{ text-align: center; font-size: 15px; margin-bottom: 18px; letter-spacing: 2px; }}
 .row {{ display: flex; align-items: stretch; margin: 10px 0; break-inside: avoid; }}
 .mno {{ width: 2.2em; color: #888; font-size: 13px; padding-top: 2px; }}
 .m   {{ flex: 1; display: flex; flex-direction: column; border-left: 1.5px solid #444;
        padding: 2px 6px 6px; }}
 .row .m:last-child {{ border-right: 1.5px solid #444; }}
 .beats {{ display: flex; flex: 1; }}
 .beat {{ flex: 1; text-align: center; font-size: 21px; white-space: nowrap; }}
 .chord {{ min-height: 76px; text-align: center; }}
 .cname {{ font-size: 14px; font-weight: 700; color: #1a5c1a; margin: 1px 0 0;
         font-family: Georgia, "Times New Roman", serif; }}
 .fret  {{ display: block; margin: 0 auto; }}
 .n   {{ position: relative; display: inline-block; min-width: .95em; text-align: center;
        margin: 0 .10em; padding: 0 1px; }}
 .u1  {{ border-bottom: 1.5px solid #111; }}
 .u2  {{ border-bottom: 3.5px double #111; }}
 .u1 .dot.lo, .u2 .dot.lo {{ bottom: -8px; }}
 .dot {{ position: absolute; left: 50%; width: 3.5px; height: 3.5px; border-radius: 50%;
        background: #111; transform: translateX(-50%); }}
 .rest {{ color: #666; }}
 .lyr {{ display: block; font-size: 12px; font-weight: 400; line-height: 1.15;
        color: #333; margin-top: 1px; font-family: "KaiTi","SimSun",serif; }}
 .m   {{ padding-bottom: 16px; }}
 .ft  {{ margin-top: 26px; font-size: 12px; color: #999; text-align: center; }}
 @media print {{ body {{ margin: 8mm auto; }} .row {{ margin: 14px 0; }} }}
</style></head><body>
<h1>{_html.escape(title)}</h1>
<div class="meta">{_html.escape(key_str)}&nbsp;&nbsp;♩={bpm:.0f}&nbsp;&nbsp;{beats_per_bar}/4</div>
{''.join(rows_html)}
<div class="ft">本地开源流水线生成: ffmpeg + demucs + basic-pitch + librosa · 八度点在数字上/下方 · 下划线=八分(单线)/十六分(双线) · —延音 · 0休止</div>
</body></html>"""
    path.write_text(doc, encoding='utf-8')


# ------------------------------------------------- 阶段6: jianpu-ly / LilyPond 出版级 PDF
def _jly_pitch_token(e: dict, tonic_pc: int) -> str:
    """音高+变音+八度 → jianpu-ly 记号数字部分 (时值前缀由拍形决定)"""
    d = (e['pitch'] - tonic_pc) % 12
    digit = MAJOR_DIGITS.get(d) or SHARP_DIGITS[d]
    if e['oct'] > 0:
        digit += "'" * min(e['oct'], 3)
    elif e['oct'] < 0:
        digit += ',' * min(-e['oct'], 3)
    return digit


# 每拍按音符数整形的时值前缀: 1音=四分, 2音=两个八分, 3音=八分+两十六分, 4音=四十六分
# (jianpu-ly 的 q/s 记号必须成组连杠, 且延音线 '-' 不能接在连杠拍之后)
_BEAT_SHAPES = {1: [''], 2: ['q', 'q'], 3: ['q', 's', 's'], 4: ['s', 's', 's', 's']}

# 和弦名 → \chordmode 记号: 音名用 LilyPond 荷兰记法(C→c, F#→fis), 性质用 :m/:7/...
_LILY_NOTE = ['c', 'cis', 'd', 'dis', 'e', 'f', 'fis', 'g', 'gis', 'a', 'ais', 'b']
_LILY_CHORD_SUFFIX = {'': '', 'm': ':m', '7': ':7', 'm7': ':m7', 'maj7': ':maj7'}


def _jly_chord_token(name: str, beats_per_bar: int) -> str:
    """和弦名 → 一个小节时值的 \chordmode 记号; 无和弦/未知名 → 跳过记号(时值不变)"""
    parsed = parse_chord_name(name) if name else None
    if not parsed:
        return f's1*{beats_per_bar}/4'
    pc, suffix = parsed
    return f'{_LILY_NOTE[pc]}1*{beats_per_bar}/4{_LILY_CHORD_SUFFIX[suffix]}'


def write_jly(path: Path, title: str, key_str: str, bpm: float,
              beats_per_bar: int, measures: list, tonic_pc: int, chords: dict = None) -> None:
    """measures → jianpu-ly 文本 (LilyPond 出版级排版的输入)。
    每拍精确 1 拍 → 每小节精确 = 拍号, 从构造上保证 barcheck 通过。
    chords={小节号: 和弦名} → 头部 chords=/frets= 行(ChordNames+FretBoards 吉他指法图);
    音符带 word → 头部 L: 歌词行(与音符一一同序, 休止/延音不占位, '_'=跳过)"""
    lines_toks, syls = [], []
    for m, cells in measures:
        toks = []
        prev_single = False  # 上一拍是否单 token(四分音符), 延音线只能接在它后面
        for c in cells:
            if c is None:
                toks.append('0')
                prev_single = False
            elif c == 'hold':
                if prev_single:
                    toks.append('-')     # 延音线延续前音符
                else:
                    toks.append('0')     # 连杠拍/休止后不可接 '-', 用休止
            else:
                entries = c[:4]
                shape = _BEAT_SHAPES.get(len(entries), _BEAT_SHAPES[4])[:len(entries)]
                for pref, e in zip(shape, entries):
                    toks.append(pref + _jly_pitch_token(e, tonic_pc))
                    syls.append(e.get('word') or '_')
                prev_single = len(entries) == 1
        toks.append('|')
        lines_toks.append(' '.join(toks))
    header = [f'title={title}', key_str, f'{beats_per_bar}/4', f'4={bpm:.0f}']
    if any(s != '_' for s in syls):
        header.append('L: ' + ' '.join(syls))
    if chords:
        chord_map = chords if isinstance(chords, dict) else dict(chords)
        header.append('chords=' + ' '.join(_jly_chord_token(chord_map.get(m), beats_per_bar)
                                           for m, _ in measures))
        header.append('frets=guitar')
    path.write_text('\n'.join(header) + '\n' + '\n'.join(lines_toks) + '\n',
                    encoding='utf-8')


def render_lilypond_pdf(jly_path: Path, outdir: Path,
                        show_repeated_chords: bool = False) -> Path:
    """jianpu-ly → .ly → lilypond → jianpu.pdf。
    show_repeated_chords: 把 jianpu-ly 硬编码的 chordChanges=##t 改写为 ##f,
    让连续相同的和弦也逐小节重复显示(弹唱谱"每小节都标"样式)"""
    jexe = shutil.which('jianpu-ly') or str(Path(sys.executable).with_name('jianpu-ly.exe'))
    ly_path = outdir / 'score.ly'
    with open(jly_path, 'rb') as fin:
        r1 = subprocess.run([jexe], stdin=fin, capture_output=True)
    if r1.returncode != 0:
        raise RuntimeError(f'jianpu-ly 失败: {r1.stderr[-400:]!r}')
    ly = r1.stdout.decode('utf-8', errors='replace')
    if show_repeated_chords and r'\set chordChanges = ##t' in ly:
        ly = ly.replace(r'\set chordChanges = ##t', r'\set chordChanges = ##f', 1)
    ly_path.write_text(ly, encoding='utf-8')
    lily = shutil.which('lilypond') or str(VENDOR_DIR / 'lilypond' / 'bin' / 'lilypond.exe')
    if not Path(lily).exists():
        raise FileNotFoundError('未找到 lilypond (vendor/lilypond 或 PATH)')
    env = os.environ.copy()
    env['PATH'] = str(VENDOR_DIR / 'lilypond' / 'bin') + os.pathsep + env.get('PATH', '')
    pdf = outdir / 'jianpu.pdf'
    try:                       # Windows: 旧 PDF 被阅读器占用时 lilypond 重命名会失败
        pdf.unlink(missing_ok=True)
    except OSError:
        raise RuntimeError('旧的 jianpu.pdf 被其他程序占用, 请关闭 PDF 阅读器后重试')
    r2 = subprocess.run([lily, '-dno-point-and-click', '-o', str(outdir / 'jianpu'),
                         str(ly_path)], capture_output=True, text=True,
                        encoding='utf-8', errors='replace', env=env, cwd=str(outdir))
    pdf = outdir / 'jianpu.pdf'
    if r2.returncode != 0 or not pdf.exists():
        raise RuntimeError(f'lilypond 失败:\n{(r2.stderr or r2.stdout or "")[-500:]}')
    return pdf


# ------------------------------------------------- 阶段7: FunASR 歌词 (实验性)
def extract_lyrics_chars(vocal_wav: Path, out_txt: Path):
    """FunASR paraformer-zh (字符级时间戳) → [(字, start_s, end_s), ...]"""
    from funasr import AutoModel
    model = AutoModel(model='paraformer-zh', vad_model='fsmn-vad', disable_update=True)
    res = model.generate(input=str(vocal_wav))
    item = res[0] if res else {}
    text, ts = item.get('text', ''), item.get('timestamp') or []
    if out_txt is not None:
        out_txt.write_text(text, encoding='utf-8')
    chars = [c for c in text if ('\u4e00' <= c <= '\u9fa5') or (c.isascii() and c.isalnum())]
    return [(c, s / 1000.0, e / 1000.0) for c, (s, e) in zip(chars, ts)]


def attach_lyrics(notes: list, chars: list) -> None:
    """把字按时间重叠分配给音符（重叠最大者），同音符多字拼接"""
    import bisect as _b
    if not chars or not notes:
        return
    starts = [n['start'] for n in notes]
    for c, s, e in chars:
        i = _b.bisect_right(starts, e) - 1
        best, best_ov = None, 0.0
        for j in range(max(0, i - 2), min(len(notes), i + 3)):
            n = notes[j]
            ov = min(n['end'], e) - max(n['start'], s)
            if ov > best_ov:
                best, best_ov = j, ov
        if best is not None and best_ov > 0.0:
            notes[best]['word'] = notes[best].get('word', '') + c


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description='MP3/MP4 → 每小节人声简谱（本地开源流水线）')
    ap.add_argument('input', help='输入音频/视频 (mp3/mp4/wav/flac/m4a...)')
    ap.add_argument('-o', '--outdir', default='output', help='输出目录 (默认 output)')
    ap.add_argument('--no-separate', action='store_true', help='跳过人声分离(清唱/纯人声输入)')
    ap.add_argument('--model', default='htdemucs', help='demucs 模型 (默认 htdemucs)')
    ap.add_argument('--beats-per-measure', type=int, default=None,
                    help='每小节拍数 (默认由 downbeat 自动推断, 如 4/4 填 4)')
    ap.add_argument('--bpm', type=float, default=None, help='手动指定速度(自动追踪不准时)')
    ap.add_argument('--bar-shift', type=int, default=0, help='小节线整体平移的拍数(仅 librosa 引擎生效)')
    ap.add_argument('--key', default=None, help="手动指定调号, 如 C / Am / '1=D'")
    ap.add_argument('--onset-threshold', type=float, default=0.5, help='basic-pitch 起音阈值')
    ap.add_argument('--frame-threshold', type=float, default=0.3, help='basic-pitch 帧阈值')
    ap.add_argument('--min-note-len', type=float, default=0.09, help='最短音符秒数')
    ap.add_argument('--show-octave', action='store_true', help='显示八度点(^高 _低)')
    ap.add_argument('--measures-per-line', type=int, default=4,
                    help='乐谱每行显示的小节数 (默认4)')
    ap.add_argument('--transcriber', choices=['auto', 'some', 'basic-pitch'], default='auto',
                    help='音符转写引擎: some=歌声专用(默认尝试), basic-pitch=通用回退')
    ap.add_argument('--beat-engine', choices=['auto', 'beat-this', 'librosa'], default='auto',
                    help='节拍引擎: beat-this 输出真实 downbeat=小节线(默认尝试), librosa=回退')
    ap.add_argument('--beat-model', default='best',
                    help="beat_this 模型: best=final0(78MB,已缓存则用)/small0 回退; 可显式指定 small0/final0")
    ap.add_argument('--no-pdf', action='store_true', help='跳过 jianpu-ly/LilyPond PDF 生成')
    ap.add_argument('--no-lyrics', action='store_true', help='跳过 FunASR 歌词识别(实验性)')
    ap.add_argument('--no-chords', action='store_true',
                    help='跳过和弦检测(每小节和弦名+吉他指法图)')
    args = ap.parse_args()

    t0 = time.time()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    work = outdir / 'work'
    work.mkdir(exist_ok=True)

    # 1. 抽音频
    mix_wav = work / 'mix.wav'
    log(f"① 音频抽取: {args.input}")
    extract_wav(Path(args.input), mix_wav)

    # 2. 人声分离
    if args.no_separate:
        vocal_wav = mix_wav
        log("② 跳过人声分离 (--no-separate)")
    else:
        vocal_wav = separate_vocals(mix_wav, work / 'separated', args.model)
        shutil.copy2(vocal_wav, outdir / 'vocals.wav')
        vocal_wav = outdir / 'vocals.wav'

    # 3. 节拍 (beat_this 的 downbeat 即小节线; 失败回退 librosa)
    import soundfile as sf
    duration = float(sf.info(str(mix_wav)).duration)
    beat_engine, downbeats = 'librosa', None
    if args.beat_engine in ('auto', 'beat-this'):
        beat_model = _resolve_beat_model(args.beat_model)
        try:
            log(f"     beat_this 模型: {beat_model}" + (" (best→已缓存final0)" if args.beat_model == 'best' else ""))
            bpm, beats, downbeats = track_beats_beat_this(mix_wav, beat_model)
            beat_engine = 'beat-this'
            if args.bpm:  # 手动 BPM 覆盖(纯人声易出现倍速歧义)
                bpm = args.bpm
                log(f"③ 节拍: beat_this, 手动 BPM={bpm:.0f} 覆盖, "
                    f"downbeat 小节线 {len(downbeats)} 个")
            else:
                log(f"③ 节拍: beat_this {bpm:.1f} BPM, downbeat 小节线 {len(downbeats)} 个")
        except Exception as e:
            if args.beat_engine == 'beat-this':
                sys.exit(f"错误: 指定 --beat-engine beat-this 但失败: {e}")
            log(f"③ 节拍: beat_this 不可用({type(e).__name__}: {str(e)[:100]}), 回退 librosa")
            bpm, beats, duration = track_beats(mix_wav, args.bpm)
    else:
        bpm, beats, duration = track_beats(mix_wav, args.bpm)
    beat_len = 60.0 / (bpm or 90.0)

    # 4. 音符转写 (SOME 歌声专用 → basic-pitch 通用回退)
    trans_engine = 'basic-pitch'
    notes = None
    if args.transcriber in ('auto', 'some'):
        try:
            raw_notes, some_mid = transcribe_notes_some(vocal_wav, work)
            notes = monophonic_cleanup(merge_tiny_and_filter(raw_notes, args.min_note_len))
            trans_engine = 'some'
            shutil.copy2(some_mid, outdir / 'melody.mid')
            log(f"④ 转写: SOME 歌声专用引擎 ({len(notes)} 个音符)")
        except Exception as e:
            if args.transcriber == 'some':
                sys.exit(f"错误: 指定 --transcriber some 但失败: {e}")
            log(f"④ 转写: SOME 不可用({type(e).__name__}: {str(e)[:100]}), 回退 basic-pitch")
    if notes is None:
        notes, bp_out = transcribe_notes(vocal_wav, args.onset_threshold,
                                         args.frame_threshold, args.min_note_len, beat_len)
        save_midi(bp_out, outdir / 'melody.mid')
        log(f"④ 转写: basic-pitch 通用引擎 ({len(notes)} 个音符)")
    if not notes:
        sys.exit("错误: 没有识别到音符。可尝试降低 --onset-threshold 0.3 / --frame-threshold 0.2")

    # 5. 拍号 + 分小节网格
    if args.beats_per_measure:
        bpb = args.beats_per_measure
    elif beat_engine == 'beat-this':
        bpb = infer_beats_per_measure(downbeats, beat_len)
        log(f"     拍号自动推断: 每小节 {bpb} 拍 (downbeat 间距/拍长)")
    else:
        bpb = 4
    if beat_engine == 'beat-this':
        import numpy as np
        bar_med = float(np.median(np.diff(downbeats))) if len(downbeats) > 1 else 0.0
        expected_bar = bpb * beat_len
        if abs(bar_med - expected_bar) > 0.33 * expected_bar:
            log(f"     警告: downbeat 间距 {bar_med:.2f}s 与 {bpb}拍×{beat_len:.2f}s 不符"
                f"(纯人声输入常见), 改用均匀小节网格")
            bars, _ = build_bar_grid(beats, duration, bpb, args.bar_shift, bpm or 90.0)
        else:
            bars = build_bar_grid_dbt(downbeats, duration, beat_len * bpb)
    else:
        bars, _ = build_bar_grid(beats, duration, bpb, args.bar_shift, bpm or 90.0)

    # 6. 调号（强拍位置加权: 主音/属音倾向落在小节重拍上）
    for n in notes:
        _, bi = locate_note(n['start'], bars, beat_len, bpb)
        n['w'] = 2.2 if bi == 0 else (1.3 if bpb >= 4 and bi == bpb // 2 else 1.0)
    det_tonic, det_mode, corr = estimate_key(notes)
    if args.key:
        tonic_pc, mode = parse_key_arg(args.key)
        log(f"⑤ 调号: 手动指定 1={NOTE_NAMES[tonic_pc]}"
            f"（自动检测: {NOTE_NAMES[det_tonic]}{'m' if det_mode == 'minor' else ''} 未采用）")
    else:
        tonic_pc, mode = det_tonic, det_mode
        if mode == 'minor':  # 简谱惯例: 小调按关系大调记谱
            tonic_pc = (tonic_pc + 3) % 12
            log(f"⑤ 调号: 检测到 {NOTE_NAMES[det_tonic]}m 小调(置信度{corr:.2f}), "
                f"按关系大调 1={NOTE_NAMES[tonic_pc]} 记谱")
        else:
            log(f"⑤ 调号: 1={NOTE_NAMES[tonic_pc]} (置信度 {corr:.2f})")
    pitches = sorted(n['pitch'] for n in notes)
    ref_midi = pitches[len(pitches) // 2]

    # 7. FunASR 歌词 (实验性): 分离人声 → 字符级时间戳 → 挂到音符
    if not args.no_lyrics:
        try:
            lyric_chars = extract_lyrics_chars(vocal_wav, outdir / 'lyrics.txt')
            attach_lyrics(notes, lyric_chars)
            log(f"⑥ 歌词: FunASR 识别 {len(lyric_chars)} 字 (实验性, --no-lyrics 可关)")
        except Exception as e:
            log(f"⑥ 歌词: FunASR 不可用({type(e).__name__}: {str(e)[:100]}), 跳过")

    # 7. 和弦检测(吉他弹唱谱): 伴奏轨优先, 每小节一个和弦, 失败可跳过
    chords = None
    if not args.no_chords:
        try:
            acc = sorted(work.glob('separated/*/mix/no_vocals.wav'))
            chord_src = acc[0] if acc else mix_wav
            prior_tonic, prior_mode = ((parse_key_arg(args.key)) if args.key
                                       else (det_tonic, det_mode))
            chords = detect_chords(chord_src, bars, beat_len, bpb,
                                   prior_tonic, prior_mode)
            named = [c for c in chords.values() if c]
            top = ' '.join(f'{k}×{v}' for k, v in
                           Counter(named).most_common(4))
            log(f"⑦ 和弦: {len(named)}/{len(chords)} 小节"
                f"({'伴奏轨' if acc else '全混音'}·chroma 模板) 常用 {top}")
        except Exception as e:
            log(f"⑦ 和弦: 检测失败({type(e).__name__}: {str(e)[:100]}), 跳过")

    # 8. 乐谱版式输出: 每行 N 小节 + 网页乐谱 + jianpu-ly PDF
    measures = build_measure_cells(notes, bars, beat_len, bpb, tonic_pc, ref_midi)
    rows, one_line = render_score_rows(measures, tonic_pc, args.show_octave,
                                       args.measures_per_line, chords)
    write_score_html(outdir / 'jianpu.html', Path(args.input).stem,
                     f"1={NOTE_NAMES[tonic_pc]}", bpm, bpb,
                     measures, tonic_pc, args.measures_per_line, chords)

    # 输出文件
    with open(outdir / 'jianpu.txt', 'w', encoding='utf-8') as f:
        f.write(f"输入: {args.input}\n调号: 1={NOTE_NAMES[tonic_pc]}"
                f"{'(小调,关系大调记谱)' if not args.key and det_mode == 'minor' else ''}\n"
                f"速度: {bpm:.1f} BPM   每小节{bpb}拍   "
                f"引擎: {trans_engine}+{beat_engine}\n"
                f"小节数: {measures[-1][0] if measures else 0}\n"
                + '-' * 62 + '\n')
        f.write('\n'.join(rows))
        f.write('\n' + '-' * 62 + f'\n整曲: {one_line}\n')

    with open(outdir / 'notes.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['小节', '拍', '开始(s)', '结束(s)', '时长(s)', '音名', 'MIDI',
                    '简谱', '字', '力度', '和弦'])
        chord_map = chords or {}
        for n in sorted(notes, key=lambda x: x['start']):
            m, bi = locate_note(n['start'], bars, beat_len, bpb)
            name = NOTE_NAMES[n['pitch'] % 12] + str(n['pitch'] // 12 - 1)
            w.writerow([m, bi + 1, f"{n['start']:.2f}", f"{n['end']:.2f}",
                        f"{n['end'] - n['start']:.2f}", name, n['pitch'],
                        pitch_to_jianpu(n['pitch'], tonic_pc, args.show_octave, ref_midi),
                        n.get('word', ''), f"{n['amp']:.2f}", chord_map.get(m) or ''])

    # jianpu-ly → LilyPond 出版级 PDF (可降级)
    pdf_note = ''
    if not args.no_pdf:
        jly_path = outdir / 'score.jly'
        write_jly(jly_path, Path(args.input).stem, f"1={NOTE_NAMES[tonic_pc]}",
                  bpm, bpb, measures, tonic_pc, chords)
        try:
            render_lilypond_pdf(jly_path, outdir, show_repeated_chords=bool(chords))
            pdf_note = ' / jianpu.pdf'
        except Exception as e:
            log(f"警告: PDF 生成失败({str(e)[:140]}); 已保留 score.jly 供手动排版")

    print('\n'.join(rows))
    print('-' * 62)
    print(f"整曲: {one_line}")
    log(f"完成 [OK] 用时 {time.time() - t0:.1f}s → {outdir}/ (jianpu.txt / jianpu.html{pdf_note} / "
        "notes.csv / melody.mid" + (' / vocals.wav' if not args.no_separate else '') + ")")


if __name__ == '__main__':
    main()
