# autoresearch

> 默认面向 **NVIDIA GPU**。若在 Mac（MPS）或纯 CPU 上跑，请改用控制台的 **macOS / CPU** 指引（或打开 `program_macos_zh.md` / `program_cpu_zh.md`）。

这是一个让 LLM 自主做研究的实验。

## 设置

开始新实验前，先与用户一起完成：

1. **商定运行标签**：按当天日期提议标签（例如 `mar5`）。分支 `autoresearch/<tag>` 必须尚不存在——这是一次全新运行。
2. **创建分支**：从当前 master 执行 `git checkout -b autoresearch/<tag>`。
3. **阅读范围内文件**：仓库很小，请读完这些文件建立上下文：
   - `README.md` — 仓库背景。
   - `prepare.py` — 固定常量、数据准备、分词器、数据加载器、评估。**不要修改**。
   - `train.py` — 你唯一可以改的文件：模型架构、优化器、训练循环。
4. **确认数据存在**：检查 `~/.cache/autoresearch/` 是否已有数据分片与分词器。若没有，请人类运行 `uv run prepare.py`。
5. **初始化 results.tsv**：创建只含表头的 `results.tsv`，基线会在第一次跑完后写入。
6. **确认后开始**：确认设置无误，再进入实验。

获得确认后，立刻启动实验循环。

## 实验

每次实验在单卡上运行。训练脚本有**固定 5 分钟**挂钟训练预算（不含启动/编译）。启动方式：`uv run train.py`。

**你可以做：**
- 修改 `train.py`——这是唯一可编辑文件。架构、优化器、超参、训练循环、batch、模型大小等全部可以改。

**你不可以做：**
- 修改 `prepare.py`。它是只读的，包含固定评估、数据加载、分词器与训练常量（时间预算、序列长度等）。
- 安装新包或增加依赖。只能使用 `pyproject.toml` 里已有的包。
- 改动评估链路。`prepare.py` 里的 `evaluate_bpb` 是唯一权威指标。

**目标很简单：把 val_bpb 降到最低。** 时间预算固定，所以不必纠结训练时长——永远是 5 分钟。架构、优化器、超参、batch、模型大小都可试。唯一硬约束：代码不崩，并在预算内跑完。

**显存（VRAM）**是软约束。为了有意义的 val_bpb 提升，可以适度增加；但不要爆炸式上涨。

**简单性标准**：其他条件相近时，更简单更好。为一点点提升加上丑陋复杂度，通常不值。反过来，删掉东西却持平或更好——那是简化胜利，应保留。判断是否 keep 时，要权衡复杂度成本与收益幅度。加 20 行 hack 只换 0.001？多半不值。删代码换 0.001？一定 keep。几乎没提升但代码更干净？keep。

**第一次运行**：永远先跑基线——原样执行当前 `train.py`，不要先改代码。

## 输出格式

脚本结束后会打印类似摘要：

```
---
val_bpb:          0.997900
training_seconds: 300.1
total_seconds:    325.9
peak_vram_mb:     45060.2
mfu_percent:      39.80
total_tokens_M:   499.6
num_steps:        953
num_params_M:     50.3
depth:            8
```

脚本总会在约 5 分钟后停，具体数字取决于本机算力。关键指标可从日志提取：

```
grep "^val_bpb:" run.log
```

## 记录结果

实验结束后写入 `results.tsv`（**制表符分隔**，不要用逗号——描述里的逗号会弄乱列）。

表头与 5 列：

```
commit	val_bpb	memory_gb	status	description
```

1. git 短哈希（7 位）
2. 得到的 val_bpb（如 `1.234567`）；崩溃记 `0.000000`
3. 峰值显存 GB，保留一位小数（`peak_vram_mb / 1024`）；崩溃记 `0.0`
4. 状态：`keep`、`discard` 或 `crash`
5. 简短描述：这次试了什么

示例：

```
commit	val_bpb	memory_gb	status	description
a1b2c3d	0.997900	44.0	keep	baseline
b2c3d4e	0.993200	44.2	keep	increase LR to 0.04
c3d4e5f	1.005000	44.0	discard	switch to GeLU activation
d4e5f6g	0.000000	0.0	crash	double model width (OOM)
```

## 实验循环

实验在专用分支上进行（例如 `autoresearch/mar5` 或 `autoresearch/mar5-gpu0`）。

永久循环：

1. 查看当前 git 分支/提交
2. 直接改 `train.py`，写入一个实验想法
3. `git commit`
4. 跑实验：`uv run train.py > run.log 2>&1`（全部重定向——不要用 tee，别让输出淹没上下文）
5. 读结果：`grep "^val_bpb:\|^peak_vram_mb:" run.log`
6. 若 grep 为空，说明崩溃了。用 `tail -n 50 run.log` 看堆栈并尝试修复；多次仍不行就放弃该想法
7. 把结果记入 tsv（**不要提交** `results.tsv`，保持未跟踪）
8. 若 val_bpb 变好（更低）：推进分支，保留这次 commit
9. 若持平或变差：`git reset` 回到改之前

你是完全自主的研究者：有效就 keep，无效就 discard，靠推进分支持续迭代。真的卡住才考虑 rewind，而且应极其罕见。

**超时**：单次实验大约 5 分钟（加少量启动/评估开销）。超过 10 分钟就杀掉，当作失败（discard 并回退）。

**崩溃**：OOM、bug 等按判断处理。若是明显笔误/缺 import，修好重跑；若想法本身不通，跳过，在 tsv 记 `crash`，继续下一个。

**永不停止**：实验循环一旦开始（设置完成后），不要停下来问人类「要不要继续」。人类可能在睡觉或不在电脑旁，期望你**一直**干到被手动打断。没想法就再想：读代码里引用的论文、重读范围内文件找新角度、组合接近成功的改动、试更激进的架构。循环直到人类打断为止。

举例：用户睡觉时把你挂着跑。每次约 5 分钟，大约 12 次/小时，一晚可跑约 100 次。早上醒来，实验结果已经全部由你完成。
