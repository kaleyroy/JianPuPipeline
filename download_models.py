#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型预下载 / 环境自检工具

用法:
  python download_models.py                    # 自检 + 下载缺失的 beat_this final0
  python download_models.py --proxy http://127.0.0.1:7897   # 全程走代理
  python download_models.py --check            # 只自检不下载

网络说明:
  - 默认源为 beat_this 官方 JKU 云盘(国内极慢 ~10KB/s)
  - 自动回退 HuggingFace 镜像 hf-mirror.com(国内直连 ~300KB/s)
  - GitHub 下载建议走代理或 gh-proxy.com 前缀(见 AGENTS.md)
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# beat_this 官方云盘 + HF 镜像备源(Audante/beat-this-final0 上的原版 Lightning ckpt)
FINAL0_SOURCES = [
    "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt",
    "https://hf-mirror.com/Audante/beat-this-final0/resolve/main/beat_this-final0.ckpt",
]
HUB_DIR = Path.home() / '.cache' / 'torch' / 'hub' / 'checkpoints'
ROOT = Path(__file__).resolve().parent
FINAL0_SIZE = 81_000_000  # 官方 ~77.3MiB, 校验下限

# 注: SOME 的 RMVPE 音高模型不需要下载 —— v1.0.0-baseline 推理时 f0 输入为全零
# (见 vendor/SOME/inference/me_infer.py 第33-58行, f0 提取被注释), RMVPE 不参与推理。


def log(msg):
    print(f"[download_models] {msg}", flush=True)


def probe_speed(url: str, proxy: str = None) -> float:
    """拉取 1MB 测速, 返回 B/s (失败返回 -1)"""
    env = os.environ.copy()
    if proxy:
        env['http_proxy'] = env['https_proxy'] = proxy
    r = subprocess.run(['curl', '-sL', '--max-time', '15', '-r', '0-1048575',
                        '-o', os.devnull, '-w', '%{speed_download}', url],
                       capture_output=True, text=True, env=env)
    try:
        return float(r.stdout.strip() or -1)
    except ValueError:
        return -1.0


def curl_download(url: str, dest: Path, proxy: str = None, min_size: int = 1000) -> bool:
    """带断点续传的下载; 返回是否成功(大小达标)"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if proxy:
        env['http_proxy'] = env['https_proxy'] = proxy
    for attempt in range(40):
        cmd = ['curl', '-sL', '-C', '-', '--max-time', '1500',
               '--speed-limit', '2048', '--speed-time', '30',
               '-o', str(dest), url]
        r = subprocess.run(cmd, env=env)
        if r.returncode == 0 and dest.exists() and dest.stat().st_size >= min_size:
            return True
        time.sleep(3)
    return dest.exists() and dest.stat().st_size >= min_size


def fmt_size(p: Path) -> str:
    return f"{p.stat().st_size / 1048576:.1f}MB" if p.exists() else "缺失"


def status_table() -> list:
    """自检所有本地模型资产 → [(名称, 状态, 路径)]"""
    def ok_size(p: Path, min_mb: float) -> str:
        if p.exists() and p.stat().st_size >= min_mb * 1048576:
            return "OK " + fmt_size(p)
        return "缺失"

    rows = []
    f0 = HUB_DIR / 'beat_this-final0.ckpt'
    st = ok_size(f0, 70)
    rows.append(("beat_this final0 (78MB, 最准)",
                 st if st.startswith('OK') else "缺失(可下载)", str(f0)))
    s0 = HUB_DIR / 'beat_this-small0.ckpt'
    st = ok_size(s0, 7)
    rows.append(("beat_this small0 (8MB, 回退)",
                 st if st.startswith('OK') else "缺失(首次运行自动下载)", str(s0)))
    some_ckpts = list((ROOT / 'vendor' / 'SOME' / 'pretrained').glob('*/model_ckpt*.ckpt'))
    rows.append(("SOME 歌声转写模型 (已是官方最佳)",
                 "OK " + fmt_size(some_ckpts[0]) if some_ckpts else "缺失",
                 str(some_ckpts[0]) if some_ckpts else "vendor/SOME/pretrained/"))
    lily = ROOT / 'vendor' / 'lilypond' / 'bin' / ('lilypond.exe' if os.name == 'nt' else 'lilypond')
    rows.append(("LilyPond 2.24 (PDF 排版)", "OK" if lily.exists() else "缺失", str(lily)))
    ms = Path.home() / '.cache' / 'modelscope' / 'models'
    rows.append(("FunASR paraformer (歌词,~1GB)",
                 "OK" if any(ms.glob('*paraformer*')) else "缺失(首次运行自动下载)", str(ms)))
    dem = Path.home() / '.cache' / 'huggingface' / 'hub' / 'models--adefossez--HTDemucs'
    rows.append(("demucs htdemucs (人声分离,~80MB)",
                 "OK" if any(dem.glob('snapshots/*/*')) else "缺失(首次运行自动下载)", str(dem)))
    return rows


def main():
    ap = argparse.ArgumentParser(description='模型预下载 / 环境自检')
    ap.add_argument('--proxy', default=os.environ.get('https_proxy') or os.environ.get('http_proxy'),
                    help='HTTP 代理, 如 http://127.0.0.1:7897 (默认读环境变量)')
    ap.add_argument('--check', action='store_true', help='只自检, 不下载')
    args = ap.parse_args()

    rows = status_table()
    log("== 本地模型资产自检 ==")
    for name, st, path in rows:
        print(f"  [{'OK ' if st.startswith('OK') else '-- '}] {name}: {st}")

    if args.check:
        return 0

    target = HUB_DIR / 'beat_this-final0.ckpt'
    if target.exists() and target.stat().st_size >= FINAL0_SIZE:
        log("final0 已存在, 无需下载")
        return 0
    log(f"开始下载 beat_this final0 (78MB)  代理: {args.proxy or '无(直连)'}")
    # 先对每个源测速(拉1MB), 选最快的源下载, 避免在慢源上耗尽重试次数
    best_url, best_speed = None, -1.0
    for i, url in enumerate(FINAL0_SOURCES):
        sp = probe_speed(url, proxy=args.proxy)
        log(f"源{i + 1} 测速: {sp / 1024:.0f} KB/s  {url}")
        if sp > best_speed:
            best_url, best_speed = url, sp
    if best_speed <= 0:
        log("全部源不可达。建议启用代理后重试:")
        log('  PowerShell: $env:http_proxy="http://127.0.0.1:7897"; $env:https_proxy="http://127.0.0.1:7897"')
        log('  bash:       export http_proxy=http://127.0.0.1:7897 https_proxy=http://127.0.0.1:7897')
        return 1
    log(f"选定最快源 ({best_speed / 1024:.0f} KB/s), 开始断点续传下载...")
    if not curl_download(best_url, target, proxy=args.proxy, min_size=FINAL0_SIZE):
        log("下载失败。建议启用代理(见上方命令)或稍后重试(已保留断点)。")
        return 1
    log(f"下载完成: {target} ({fmt_size(target)})")
    log("自检(下载后):")
    for name, st, path in status_table():
        print(f"  [{'OK ' if st.startswith('OK') else '-- '}] {name}: {st}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
