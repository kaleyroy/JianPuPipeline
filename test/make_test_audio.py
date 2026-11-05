#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成带已知简谱答案的合成测试音频（模拟人声旋律 + 伴奏混音）"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
BPM = 100
Q = 60.0 / BPM  # 四分音符时长

# C 大调音级 → 半音
DEG_SEMI = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}
BASE = 60  # C4

# 已知答案: 每小节 4 个四分音符; 负数表示低八度 (如 -5 = 低音5)
BARS = [
    [1, 1, 2, 2],
    [3, 3, 5, 3],
    [4, 4, 3, 2],
    [1, 1, 5, -5],
    [6, 6, 5, 4],
    [3, 3, 2, 2],
    [7, 6, 5, 4],
    [5, 4, 2, 1],
]


def midi2freq(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def synth_voice_note(freq, dur, amp=0.6):
    """模拟人声单音: 基频+泛音+缓慢颤音+包络"""
    n = int(SR * dur)
    t = np.arange(n) / SR
    # 颤音 (5.2Hz, 0.4% 深度, 120ms 渐入) —— 用积分保证相位连续
    vib = 0.004 * np.sin(2 * np.pi * 5.2 * t) * np.minimum(t / 0.12, 1.0)
    phase_t = np.cumsum(1.0 + vib) / SR
    ph = 2 * np.pi * freq * phase_t
    x = (np.sin(ph) + 0.28 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)) / 1.4
    env = np.minimum(t / 0.015, 1.0) * np.minimum((dur - t) / 0.06, 1.0).clip(0, 1) \
        * np.exp(-0.35 * t)
    return amp * x * env.clip(0, 1)


def synth_melody():
    total = len(BARS) * 4 * Q + 0.6
    y = np.zeros(int(total * SR))
    for bar in BARS:
        pass
    t_cursor = 0.0
    for bar in BARS:
        for deg in bar:
            m = BASE + DEG_SEMI[abs(deg)] + (-12 if deg < 0 else 0)
            note = synth_voice_note(midi2freq(m), Q - 0.05)
            i = int(t_cursor * SR)
            y[i:i + len(note)] += note
            t_cursor += Q
    return y


def synth_accompaniment(total_samples):
    """鼓 + 和弦垫的简单伴奏"""
    y = np.zeros(total_samples)
    bar_len = 4 * Q
    n_bars = int(total_samples / SR / bar_len) + 1
    chords = [[48, 52, 55], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # C F C G
    for b in range(n_bars):
        t0 = b * bar_len
        # kick: 每拍
        for k in range(4):
            i = int((t0 + k * Q) * SR)
            n = min(int(0.12 * SR), total_samples - i)
            if n <= 0:
                continue
            tt = np.arange(n) / SR
            y[i:i + n] += 0.9 * np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 30)
        # hihat: 每半拍
        for k in range(8):
            i = int((t0 + k * Q / 2) * SR)
            n = min(int(0.03 * SR), total_samples - i)
            if n <= 0:
                continue
            y[i:i + n] += 0.18 * np.random.default_rng(7).uniform(-1, 1, n) * np.exp(-np.arange(n) / (SR * 0.006))
        # pad: 每小节一个和弦
        chord = chords[b % 4]
        i = int(t0 * SR)
        n = min(int(bar_len * SR), total_samples - i)
        if n <= 0:
            continue
        tt = np.arange(n) / SR
        pad = sum(np.sin(2 * np.pi * midi2freq(m) * tt) for m in chord) / 3
        y[i:i + n] += 0.35 * pad * np.minimum(tt / 0.05, 1)
    return y


def main():
    data_dir = Path(__file__).resolve().parent.parent / 'data'
    data_dir.mkdir(exist_ok=True)

    melody = synth_melody()
    total = len(melody)
    song = melody + synth_accompaniment(total)
    song = 0.9 * song / np.abs(song).max()

    sf.write(data_dir / 'test_vocal.wav', melody, SR)   # 纯"人声"
    sf.write(data_dir / 'test_song.wav', song, SR)      # 带伴奏混音

    expected = ' | '.join(' '.join(str(abs(d)) for d in bar) for bar in BARS)
    (data_dir / 'expected.txt').write_text(expected, encoding='utf-8')
    print(f"生成完毕: test_vocal.wav / test_song.wav ({total / SR:.1f}s, {BPM}BPM, 8小节)")
    print(f"标准答案: {expected}")


if __name__ == '__main__':
    main()
