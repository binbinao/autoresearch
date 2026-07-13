# autoresearch（CPU）

这是面向 **纯 CPU** 的 Auto Research 指引。没有 CUDA / MPS 加速时，吞吐极低；必须用迷你配置，把「能跑完、能比较」放在第一位。

> 控制台请先点 **CPU** 预设。目标是冒烟与小步验证，不是追赶 GPU 论文数字。

## 平台现实（必读）

- 设备应是 `cpu`。
- **强制小配置**（与 CPU 预设一致，可再缩小）：
  - `AR_MAX_SEQ_LEN=256`
  - `AR_DEPTH=2`
  - `AR_WINDOW_PATTERN=L`
  - `AR_DEVICE_BATCH_SIZE=2`
  - `AR_TOTAL_BATCH_SIZE=4096`
  - `AR_EVAL_TOKENS=65536`
  - `AR_TIME_BUDGET=30`（先 30s；稳定后再考虑 60）
- 单步很慢：一次实验可能只有很少 `num_steps`。**用相对 `val_bpb` 比较**，不要和 GPU 绝对值比。
- `peak_vram_mb` 无意义（通常为 0）。
- 优先改超参 / 极小结构，避免大宽度、深网络、长上下文。

## 设置

1. 标签如 `jul12-cpu`，创建 `autoresearch/<tag>`。
2. 读 `README.md`、`prepare.py`（只读）、`train.py`。
3. 准备数据：`uv run prepare.py`（若缓存没有）。
4. 初始化 `results.tsv`；确认设备为 `cpu` 且 CPU 预设已应用。

## 实验规则

**你可以做：** 改 `train.py` 或 `AR_*`；每次只动一个很小的旋钮。  
**你不可以做：** 改 `prepare.py`、加依赖、改评估；或套用 GPU/macOS 中大配置。

**目标**：在 30–60s 预算内稳定跑完，并尽量降低 `val_bpb`。  
**第一次运行**：CPU 预设基线，不改代码。

## 推荐顺序（CPU）

1. 30s 基线  
2. 微调 LR（如 `AR_MATRIX_LR`）  
3. 仅当仍很快时，才略增 batch 或 depth（一次一个）  
4. 若经常超时：继续降 `DEPTH` / `SEQ` / `EVAL_TOKENS`

## 输出与循环

```
grep "^val_bpb:\|^device:\|^num_steps:" run.log
```

记录 tsv；`memory_gb` 可写 `0.0`，description 注明 `cpu` 与关键环境变量。

永久循环：keep / discard 规则与通用版相同。  
**超时**：30s 档若超过 ~3 分钟仍未结束就杀掉；60s 档超过 ~5 分钟杀掉。  
**永不停止**：设置完成后持续小步实验，直到人类打断。
