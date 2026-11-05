# 音频/视频 → 每小节人声简谱（全本地开源流水线）

输入一首歌（mp3/mp4/wav/flac/m4a…），自动产出**人声旋律的每小节简谱**（如 `1 1 2 2 | 3 3 5 3 | ...`），
文本 + 网页乐谱 + **出版级 PDF**，可选**歌词行**。全程本地运行，不调用任何在线服务。

> 深入文档：[ARCHITECTURE.md](ARCHITECTURE.md)（mermaid 架构/数据流/算法流程） · [AGENTS.md](AGENTS.md)（工程约定、网络代理、已知坑）

## 流水线架构

```
 mp3/mp4 ─①ffmpeg→ wav ─②demucs→ 纯人声 ─┬─③SOME(歌声专用, MIT)→音符  ─→ melody.mid
                      (Meta/MIT)          │   └回退 basic-pitch(通用)
                      └原混音→ ④beat_this(ISMIR'24, MIT)→拍+downbeat(=小节线)
                               └回退 librosa 均匀网格
                                   ⑤调号: KS+强拍加权   ⑥FunASR歌词(实验性, 字级时间戳)
                                   ⑦ 小节×拍网格 → 延音/下划线推导
      输出: jianpu.txt(4小节/行) · jianpu.html(乐谱页) · score.jly → jianpu-ly+LilyPond → jianpu.pdf
            notes.csv(含字) · lyrics.txt · vocals.wav
```

| 环节 | 首选引擎 | 回退 | 许可证 |
|---|---|---|---|
| 音频抽取 | FFmpeg | — | LGPL/GPL |
| 人声分离 | Demucs htdemucs | — | MIT |
| 音符转写 | [SOME](https://github.com/openvpi/SOME)（歌声专用，同音换字切分强） | basic-pitch | 代码 MIT；**SOME 模型权重 CC BY-NC-SA 4.0（仅限非商用）** |
| 节拍/小节线 | [beat_this](https://github.com/CPJKU/beat_this) small0（downbeat=小节线） | librosa 均匀网格 | MIT |
| 出版排版 | [jianpu-ly](https://github.com/ssb22/jianpu-ly) + LilyPond 2.24（vendor 内置） | 保留 .jly 跳过 PDF | Apache 2.0 / GPL |
| 歌词（实验性） | [FunASR](https://github.com/modelscope/FunASR) paraformer-zh | 跳过 | MIT |

任一组件缺失都会自动降级并在日志注明，流水线不中断。

## 安装

需要 **Python 3.10** venv（Windows 下 basic-pitch 走 onnxruntime 的关键）和 **FFmpeg**（PATH 中）。

```bash
# 1) Python 3.10 虚拟环境
D:/Miniconda3/envs/musician/python.exe -m venv .venv
# 2) 依赖（直连 PyPI 慢时用清华镜像）
.venv/Scripts/python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
# 3) SOME 源码 + 模型（本仓库 vendor/ 已内置；重装时）
#    源码: https://github.com/openvpi/SOME/archive/refs/heads/main.zip → vendor/SOME
#    模型: releases v1.0.0-baseline 的 0119_continuous128_5spk.zip → vendor/SOME/pretrained/
#    (GitHub 直连慢可用 gh-proxy.com 前缀; 不装则自动回退 basic-pitch)
# 4) LilyPond 已内置 vendor/lilypond (2.24.4 便携版)
```

模型自动下载：demucs（~80MB，首跑）、beat_this small0（8MB，首跑）、FunASR paraformer（~1GB，modelscope 国内直连快）。

**预下载最优模型**（推荐；`--proxy` 可选，网络说明见 `AGENTS.md`）：

```bash
.venv/Scripts/python download_models.py --check   # 只自检
.venv/Scripts/python download_models.py           # 自动测速选源下载 final0 (78MB)
```

## 使用

```bash
# 全自动（推荐）: 分离 → beat_this 小节线 → SOME 转写 → 歌词 → 文本+HTML+PDF
.venv/Scripts/python jianpu.py song.mp4 -o out

# 清唱/纯人声（beat_this 对无鼓人声有倍速歧义，护栏会自动切均匀网格；建议给 --bpm）
.venv/Scripts/python jianpu.py vocal.wav --no-separate --bpm 90 --key C

# 引擎选择 / 关闭可选阶段
.venv/Scripts/python jianpu.py song.mp3 --transcriber basic-pitch --beat-engine librosa
.venv/Scripts/python jianpu.py song.mp3 --no-lyrics --no-pdf
```

### 输出文件（-o 目录下）

| 文件 | 内容 |
|---|---|
| `jianpu.txt` | **乐谱版式文本**：每行 4 小节、行首小节编号、` \| `分隔 + 整曲单行 |
| `jianpu.html` | **网页乐谱**：八度点、八分/十六分下划线、延音 `—`、休止 `0`、歌词行 |
| `jianpu.pdf` | **出版级 PDF**（jianpu-ly + LilyPond：自动连杠/附点/延音线/小节号） |
| `score.jly` / `score.ly` | jianpu-ly 中间格式（可手工编辑后重跑 lilypond 微调排版） |
| `notes.csv` | 每音符：小节、拍、时间、音名、MIDI、简谱、**字**、力度 |
| `lyrics.txt` | FunASR 原始歌词识别 |
| `melody.mid` / `vocals.wav` | 旋律 MIDI / 分离人声 |

记号图例：`0`休止 · `—`延音(≥1.5拍) · 拍内连写如 `33`=两个八分 · 文本八度 `^`/`_`（HTML 为数字上下圆点，PDF 为标准记号）。

### 参数速查

| 参数 | 默认 | 说明 |
|---|---|---|
| `--transcriber` | auto | some(歌声专用)→basic-pitch 自动回退；可强制指定 |
| `--beat-engine` | auto | beat-this(downbeat 小节线)→librosa 自动回退 |
| `--beat-model` | best | best=final0(78MB,已缓存则用,论文平均F1更高)/small0(8MB)自动回退；可显式指定。实测两模型在常规歌曲上输出常完全一致，final0 耗时约 2 倍 |
| `--beats-per-measure` | 自动 | 由 downbeat 间距自动推断拍号；可手动指定（如 3/4 填 3） |
| `--bpm` / `--key` | 自动 | 手动覆盖；纯人声输入建议给 `--bpm` |
| `--no-lyrics` / `--no-pdf` / `--no-separate` | off | 跳过对应阶段 |
| `--bar-shift` | 0 | 小节线平移拍数（仅 librosa 引擎生效） |
| `--measures-per-line` | 4 | 文本/HTML 每行小节数（PDF 由 LilyPond 自动分行） |
| `--show-octave` / `--onset-threshold` / `--frame-threshold` / `--min-note-len` | — | 同旧版 |

## 验证（自带端到端测试）

```bash
.venv/Scripts/python test/run_test.py
```

实测（2026-11-02）：
- **beat_this**：合成鼓点 100BPM → BPM=100.0 精确，downbeat 恰为 0/2.4/4.8/7.2/9.6s 小节线 ✓
- **回归**（basic-pitch+librosa 锁定路径）：8 小节逐字节全对 ✓
- **SOME 冒烟**（歌声引擎+beat_this）：版式正确，同音换字切分显著优于 basic-pitch ✓
- 降级路径（无 SOME / 无 beat_this / 无 LilyPond）全部优雅回退 ✓

## 常见问题

- **纯人声/清唱小节乱**：beat_this 无鼓点时可能倍速，管线有自动护栏；仍乱就 `--bpm` + `--beats-per-measure`。
- **PDF 未生成**：看日志警告；`score.jly` 一定保留，可装 LilyPond 后手工 `jianpu-ly < score.jly > x.ly && lilypond x.ly`。
- **歌词识别差**：FunASR 针对说话训练，唱歌拖腔/气声效果有限（实验性），`--no-lyrics` 关闭。
- **直连 PyPI/GitHub 慢**：pip 用清华镜像；GitHub 下载用 gh-proxy.com 前缀。
- 中文文件名/GBK 控制台已兼容。

## 已知局限

- 时值记号为简化推导（延音线/下划线/附点近似）；三连音、连音线、复杂数切分不识别（PDF 中也不体现）。
- 歌词行实验性；PDF 版歌词对齐未启用（避免错位，HTML/CSV 中有）。
- 和声/双声部取主导旋律；混响极重时可能引入杂音。
- **SOME 模型权重为 CC BY-NC-SA 4.0：整套流水线仅限非商业用途**（如需商用可只用 basic-pitch 路径）。
