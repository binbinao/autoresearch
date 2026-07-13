# autoresearch

![teaser](progress.png)

*曾几何时，前沿AI研究是由肉脑计算机在吃饭、睡觉、娱乐和偶尔通过声波互联进行"组会"仪式之间完成的。那个时代早已过去。研究现在完全由在计算集群巨型结构中运行的自主AI代理群所主导。代理们声称我们现在处于代码库的第10,205代，但无论如何，没有人能判断这是对是错，因为"代码"现在是一个自我修改的二进制文件，已经超出了人类的理解范围。这个仓库是这一切如何开始的故事。-@karpathy, 2026年3月*

核心理念：给AI代理一个真实但小型的LLM训练设置，让它通宵自主实验。它修改代码，训练5分钟，检查结果是否改善，保留或丢弃，然后重复。你早上醒来时会看到实验日志和（希望是）更好的模型。这里的训练代码是[nanochat](https://github.com/karpathy/nanochat)的简化单GPU实现。核心思想是，你不再像研究人员通常那样接触任何Python文件。相反，你是在编写`program.md` Markdown文件，这些文件为AI代理提供上下文并设置你的自主研究组织。本仓库中的默认`program.md`有意保持为基本基线，但很明显如何随着时间的推移迭代它以找到实现最快研究进展的"研究组织代码"，如何添加更多代理等。关于这个项目的更多背景信息请参见[这条推文](https://x.com/karpathy/status/2029701092347630069)和[这条推文](https://x.com/karpathy/status/2031135152349524125)。

## 工作原理

仓库刻意保持小巧，真正重要的只有三个文件：

- **`prepare.py`** — 固定常量、一次性数据准备（下载训练数据，训练BPE分词器）和运行时工具（数据加载器、评估）。不修改。
- **`train.py`** — 代理编辑的单个文件。包含完整的GPT模型、优化器（Muon + AdamW）和训练循环。一切都是公平游戏：架构、超参数、优化器、批次大小等。**此文件由代理编辑和迭代**。
- **`program.md`** — 一个代理的基线指令（默认面向 NVIDIA GPU）。将你的代理指向这里并让它运行。**此文件由人类编辑和迭代**。在 Mac（MPS）或纯 CPU 上请改用 `program_macos.md` / `program_cpu.md`（及对应 `_zh`），或在本地控制台选择平台。

设计上，训练始终运行**固定的5分钟时间预算**（挂钟时间，不包括启动/编译），无论你的计算细节如何。指标是**val_bpb**（验证位每字节）— 越低越好，且与词汇表大小无关，因此可以公平比较架构变化。

如果你是神经网络新手，这个["傻瓜指南"](https://x.com/hooeem/status/2030720614752039185)看起来提供了很多背景信息。

## 快速开始

**要求：** 单个NVIDIA GPU（在H100上测试过），Python 3.10+，[uv](https://docs.astral.sh/uv/)。

```bash
# 1. 安装uv项目管理器（如果还没有）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 安装依赖
uv sync

# 3. 下载数据并训练分词器（一次性，约2分钟）
uv run prepare.py

# 4. 手动运行单个训练实验（约5分钟）
uv run train.py
```

### 小白 Web 控制台（可选）

不想记命令行的话，可以装 UI 依赖后用浏览器操作实验循环：

```bash
uv sync --extra ui
uv run --extra ui python -m web.app
```

打开 http://127.0.0.1:8765 ，说明见 [`web/README.md`](./web/README.md)。

如果以上命令都能正常工作，你的设置就正常了，可以进入自主研究模式。

## 运行代理

只需在此仓库中启动你的Claude/Codex或任何你想要的（并禁用所有权限），然后可以提示类似：

```
你好，请查看program.md，让我们开始一个新的实验！先进行设置。
```

`program.md`文件本质上是一个超轻量级的"技能"。

## 项目结构

```
prepare.py      — 常量、数据准备 + 运行时工具（不修改）
train.py        — 模型、优化器、训练循环（代理修改此文件）
program.md      — 代理指令
pyproject.toml  — 依赖项
```

## 设计选择

- **单个文件修改。** 代理只接触`train.py`。这使范围可控且差异可审查。
- **固定时间预算。** 训练始终运行恰好5分钟，无论你的特定平台如何。这意味着你可以预期大约12个实验/小时，大约100个实验在你睡觉时完成。这个设计决策有两个好处。首先，这使得实验可以直接比较，无论代理改变什么（模型大小、批次大小、架构等）。其次，这意味着autoresearch将在该时间预算内为你的平台找到最优模型。缺点是你的运行（和结果）变得无法与其他人在其他计算平台上运行的进行比较。
- **自包含。** 除了PyTorch和几个小包外没有外部依赖。没有分布式训练，没有复杂配置。一个GPU，一个文件，一个指标。

## 平台支持

此代码当前要求你有一个单独的NVIDIA GPU。原则上支持CPU、MPS和其他平台是相当可能的，但这也会使代码膨胀。我不确定现在是否想亲自承担这个。人们可以参考（或让他们的代理参考）完整/父nanochat仓库，该仓库具有更广泛的平台支持并展示了各种解决方案（例如Flash Attention 3内核回退实现、通用设备支持、自动检测等），请随意为其他平台创建分支或讨论，我很乐意在README的某个新显著分支部分等链接到它们。

鉴于似乎有很多人对在比H100小得多的计算平台上尝试autoresearch感兴趣，这里有一些额外的建议。如果你要在较小的计算机（Macbook等）上尝试运行autoresearch，我推荐下面的分支之一。除此之外，这里有一些关于如何为有抱负的分支调整较小模型的默认值的建议：

1. 为了获得半像样的结果，我会使用熵少得多的数据集，例如这个[TinyStories数据集](https://huggingface.co/datasets/karpathy/tinystories-gpt4-clean)。这些是GPT-4生成的短故事。因为数据范围窄得多，你会看到较小模型的合理结果（如果你在训练后尝试从中采样）。
2. 你可以尝试降低`vocab_size`，例如从8192降到4096、2048、1024，甚至—简单地在utf-8编码后使用字节级分词器可能只有256个字节。
3. 在`prepare.py`中，你会想要大幅降低`MAX_SEQ_LEN`，取决于计算机甚至降到256等。当你降低`MAX_SEQ_LEN`时，你可能想尝试稍微增加`train.py`中的`DEVICE_BATCH_SIZE`来补偿。每次前向/后向传递的令牌数是这两个的乘积。
4. 同样在`prepare.py`中，你会想要减少`EVAL_TOKENS`，以便你的验证损失在少得多的数据上评估。
5. 在`train.py`中，控制模型复杂度的主要单一旋钮是`DEPTH`（这里默认是8）。许多变量只是这个的函数，所以例如将其降低到4。
6. 你很可能只想使用`WINDOW_PATTERN`为"L"，因为"SSSL"使用交替带状注意力模式，可能对你非常低效。试试看。
7. 你会想要大幅降低`TOTAL_BATCH_SIZE`，但保持2的幂，例如降到`2**14`（约16K）甚至更低，很难说。

我认为这些是合理的超参数可以调整。向你最喜欢的编码代理寻求帮助，并将本指南以及完整源代码复制粘贴给它们。

## 显著分支

- [miolini/autoresearch-macos](https://github.com/miolini/autoresearch-macos) (MacOS)
- [trevin-creator/autoresearch-mlx](https://github.com/trevin-creator/autoresearch-mlx) (MacOS)
- [jsegov/autoresearch-win-rtx](https://github.com/jsegov/autoresearch-win-rtx) (Windows)
- [andyluo7/autoresearch](https://github.com/andyluo7/autoresearch) (AMD)

## 许可证

MIT