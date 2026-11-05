#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端测试:
1) 回归: basic-pitch+librosa 引擎, 输出与标准答案逐字节一致(确定性路径)
2) beat_this: downbeat 恰为小节线 (0/2.4/4.8/... @100BPM)
3) SOME+PDF 冒烟: 有 ckpt 时跑全引擎, 只断言版式结构
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'test'))
from make_test_audio import BARS  # noqa: E402

MEASURES = [' '.join(str(abs(d)) for d in bar) for bar in BARS]
EXPECTED_ONE_LINE = ' | '.join(MEASURES)
EXPECTED_ROWS = [
    f"{i * 4 + 1:>3} | " + ' | '.join(MEASURES[i * 4:(i + 1) * 4])
    for i in range((len(MEASURES) + 3) // 4)
]
PY = str(ROOT / '.venv' / 'Scripts' / 'python.exe')


def run_pipeline(outdir, extra):
    cmd = [PY, str(ROOT / 'jianpu.py'), str(ROOT / 'data' / 'test_vocal.wav'),
           '--no-separate', '--key', 'C', '--bpm', '100', '-o', str(outdir)] + extra
    print('运行:', ' '.join(cmd), '\n')
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit('FAIL: 流水线执行失败')
    return (outdir / 'jianpu.txt').read_text(encoding='utf-8')


def check_regression(text):
    ok = True
    m = re.search(r'^整曲:\s*(.+)$', text, re.M)
    if not m:
        sys.exit('FAIL: jianpu.txt 中没有整曲行')
    got_one = m.group(1).strip()
    print(f'标准答案: {EXPECTED_ONE_LINE}\n实际输出: {got_one}')
    if got_one != EXPECTED_ONE_LINE:
        ok = False
        e, g = EXPECTED_ONE_LINE.split(' | '), got_one.split(' | ')
        for i in range(max(len(e), len(g))):
            a = e[i] if i < len(e) else '(缺)'
            b = g[i] if i < len(g) else '(缺)'
            print(f'  小节{i + 1}: 期望[{a}]  实际[{b}]' + ('' if a == b else ' ←'))
    got_rows = [ln.rstrip() for ln in text.splitlines() if re.match(r'^\s*\d+ \| ', ln)]
    if got_rows != EXPECTED_ROWS:
        ok = False
        print(f'FAIL: 4小节/行版式不一致\n期望: {EXPECTED_ROWS}\n实际: {got_rows}')
    return ok


def check_beat_this():
    """beat_this 对合成鼓点应输出 100BPM + 0/2.4/4.8... 的 downbeat"""
    r = subprocess.run([PY, '-c', """
import numpy as np
from beat_this.inference import File2Beats
f2b = File2Beats(checkpoint_path='small0', device='cpu', dbn=False)
beats, downbeats = f2b(r'data/test_song.wav')
bpm = 60 / np.median(np.diff(beats))
print(f'{bpm:.1f}', ','.join(f'{float(d):.2f}' for d in downbeats[:5]))
"""], capture_output=True, text=True, cwd=str(ROOT))
    out = (r.stdout or '').strip().splitlines()
    print('beat_this:', out[-1] if out else r.stderr[-200:])
    if r.returncode != 0 or not out:
        return False
    bpm, dbs = out[-1].split(' ', 1)
    ok = abs(float(bpm) - 100.0) < 3.0
    expect = [0.0, 2.4, 4.8, 7.2, 9.6]
    got = [float(x) for x in dbs.split(',')]
    ok = ok and all(abs(a - b) < 0.15 for a, b in zip(expect, got))
    print(f'  bpm={bpm} downbeats={got} 期望≈{expect} →', 'PASS' if ok else 'FAIL')
    return ok


def check_some_smoke():
    some = ROOT / 'vendor' / 'SOME'
    if not (list(some.glob('pretrained/*.ckpt')) or list(some.glob('pretrained/**/*.ckpt'))):
        print('SOME 冒烟: SKIP (ckpt 未下载)')
        return True
    outdir = ROOT / 'output_test_some'
    text = run_pipeline(outdir, ['--transcriber', 'some', '--beat-engine', 'beat-this',
                                 '--beats-per-measure', '4', '--no-lyrics', '--no-pdf'])
    got_rows = [ln for ln in text.splitlines() if re.match(r'^\s*\d+ \| ', ln)]
    ok = len(got_rows) == 2 and 'some+beat-this' in text
    print(f'SOME 冒烟: {len(got_rows)} 行 (期望2), 引擎标记 '
          f'{"✓" if "some+beat-this" in text else "✗"} →', 'PASS' if ok else 'FAIL')
    print('\n'.join(got_rows))
    return ok


def main():
    results = {}
    results['beat_this'] = check_beat_this()
    text = run_pipeline(ROOT / 'output_test',
                        ['--transcriber', 'basic-pitch', '--beat-engine', 'librosa'])
    results['regression'] = check_regression(text)
    html = (ROOT / 'output_test' / 'jianpu.html').read_text(encoding='utf-8')
    results['html_rows'] = html.count('<div class="row">') == len(EXPECTED_ROWS)
    results['some_smoke'] = check_some_smoke()

    for k, v in results.items():
        print(f'[{k}]', 'PASS' if v else 'FAIL')
    if all(results.values()):
        print('\nALL PASS ✓')
        return 0
    sys.exit('FAIL: 存在未通过的检查')


if __name__ == '__main__':
    sys.exit(main())
