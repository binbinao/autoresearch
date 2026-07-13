# autoresearch（macOS / Apple Silicon）

这是面向 **Mac（MPS）** 的 Auto Research 指引。本机通常是统一内存，不是 NVIDIA 独显；默认 H100 配置会 OOM 或极慢。请按下面的 Mac 现实跑实验。

> 配套说明见 `MACOS_TESTING.md`。控制台请先点 **macOS** 预设，再开跑。

## 平台现实（必读）

- 设备应是 `mps`（Apple Silicon）。若落到 `cpu`，先检查 PyTorch MPS 是否可用。
- **不要用仓库默认大模型**：建议从小配置起步（与预设一致）：
  - `AR_MAX_SEQ_LEN=512`
  - `AR_DEPTH=4`
  - `AR_WINDOW_PATTERN=L`（先别用 `SSSL`）
  - `AR_DEVICE_BATCH_SIZE=8`（吃紧就降到 `4`）
  - `AR_TOTAL_BATCH_SIZE=16384`
  - `AR_EVAL_TOKENS=262144`
- **时间预算**：先用 `AR_TIME_BUDGET=60` 做冒烟与快速迭代；稳定后再逐步加到 120 / 300。
- **没有 Flash Attention 3**：注意力走标准实现，吞吐远低于 CUDA。
- **`peak_vram_mb` 在 MPS 上常常是 0**：不要用它当主内存指标；以系统内存压力、是否被系统杀掉、能否跑完为准。
- 参考量级（M4 32GB、60s 冒烟）：约 `num_params_M ≈ 11.5`，`val_bpb` 可能在 ~1.9 一带——**不要用 H100 上 ~1.0 / 50M 参数的心理预期**。

## 设置

1. **商定标签**：如 `jul12-mac`，分支 `autoresearch/<tag>` 必须不存在。
2. **创建分支**：`git checkout -b autoresearch/<tag>`。
3. **阅读文件**：`README.md`、`MACOS_TESTING.md`、`prepare.py`（只读）、`train.py`（可改）。
4. **准备数据**：`~/.cache/autoresearch/` 无数据则运行 `uv run prepare.py`。
5. **初始化** `results.tsv`（仅表头）。
6. **确认设备为 mps**，并已应用 macOS 预设环境变量。

## 实验规则

启动：`uv run train.py`（控制台会注入 `AR_*`）。

**你可以做：**
- 改 `train.py`，或主要通过 `AR_*` / 控制台旋钮调参。
- 在稳定前提下**一次只加大一个轴**：`DEPTH` → `MAX_SEQ_LEN` → `TOTAL_BATCH_SIZE` → 时间预算。

**你不可以做：**
- 改 `prepare.py`、加新依赖、改 `evaluate_bpb`。
- 一上来就按 CUDA 默认（大 depth、长上下文、`SSSL`、巨大 batch）硬刚——极易失败。

**目标**：在本机可稳定跑完的前提下，把 `val_bpb` 降到最低。  
**内存**：统一内存是硬约束。进程被系统直接杀掉 ≈ crash；先降 batch / depth / seq。

**简单性标准**：Mac 上优先「能稳定迭代」优于「复杂架构炫技」。删代码且指标不差，强烈 keep。

**第一次运行**：先跑基线（macOS 预设 + 当前 `train.py` 不改代码）。

## 推荐实验顺序（Mac）

1. 60s 冒烟基线（macOS 预设）
2. 只改学习率类标量（如 `AR_MATRIX_LR`）
3. 略增 `AR_TOTAL_BATCH_SIZE` 或 `AR_DEVICE_BATCH_SIZE`（失败就退回）
4. 再试 `AR_DEPTH` 或 `AR_MAX_SEQ_LEN`（每次只动一个）
5. 预算拉到 120s/300s 后，再考虑窗口模式等更贵改动

## 输出与记录

摘要里请看 `device`、`val_bpb`、`training_seconds`、`num_params_M`、`num_steps`。

```
grep "^val_bpb:\|^peak_vram_mb:\|^device:" run.log
```

`results.tsv` 仍为制表符分隔五列：`commit val_bpb memory_gb status description`。  
MPS 上 `memory_gb` 可记 `0.0`，在 description 里注明 `mps` 与关键 `AR_*`。

## 实验循环

永久循环：改想法 → commit → 跑训 → 读 `val_bpb` → 记 tsv → 更好则 keep，否则 discard/reset。

**超时**：冒烟 60s 档约 2 分钟内应结束；若超过预算很多仍不结束，杀掉当失败。正式 5 分钟档超过 10 分钟同样杀掉。

**崩溃**：易修的 bug 就修；若是内存/预设不匹配，先回到 macOS 预设再试，不要在错误默认上死磕。

**永不停止**：设置完成后自主迭代到被人类打断为止。卡住时回到 `MACOS_TESTING.md` 的稳定预设，换更小、更稳的改动。
