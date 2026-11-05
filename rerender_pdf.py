#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 out/notes.csv 重建 score.jly 并渲染 PDF (跳过分离/转写, 用于排版迭代)"""
import csv
from pathlib import Path

import jianpu

OUT = Path('out').resolve()
rows = list(csv.DictReader(open(OUT / 'notes.csv', encoding='utf-8-sig')))
notes = [dict(start=float(r['开始(s)']), end=float(r['结束(s)']),
              pitch=int(r['MIDI']), amp=float(r['力度']),
              word=r.get('字', '')) for r in rows]

BPM, BPB, TONIC = 125.0, 4, 7  # 1=G, 见 out/jianpu.txt 头部
beat_len = 60.0 / BPM

firsts = {}
for r in rows:
    m, bi, st = int(r['小节']), int(r['拍']), float(r['开始(s)'])
    t = st - (bi - 1) * beat_len
    if m not in firsts or t < firsts[m]:
        firsts[m] = t
bars = sorted(firsts.items())

med = sorted(n['pitch'] for n in notes)[len(notes) // 2]
measures = jianpu.build_measure_cells(notes, bars, beat_len, BPB, TONIC, med)
jianpu.write_jly(OUT / 'score.jly', '寄往未来的信', '1=G', BPM, BPB, measures, TONIC)
pdf = jianpu.render_lilypond_pdf(OUT / 'score.jly', OUT)
print('PDF:', pdf)
