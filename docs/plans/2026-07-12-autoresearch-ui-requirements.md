# 实施方案：AutoResearch 小白前端控制台

## 概述

为不会用命令行 / Agent 的用户提供本地 Web 控制台，把 `program.md` 实验循环可视化：一键准备数据、配置超参、启动 5 分钟训练、查看日志与 val_bpb、一键保留/丢弃，并持续推进 `results.tsv`。

## 需求（ECC 需求分析）

### 用户与目标
- **用户**：机器学习小白，不想记 git/uv/agent 协议
- **目标**：在浏览器里完成一次完整的 Auto Research 循环（准备 → 实验 → 比较 → 保留/丢弃 → 再试）
- **成功标准**：
  - 不打开终端也能看到环境状态、跑通一次训练（或清晰报错）
  - 能看懂当前最优 `val_bpb` 与历史实验表
  - 能编辑研究指引（`program.md`）与常见超参，无需手改 Python
  - 循环可启动/停止，状态可观测（Loop Engineering）

### 假设与约束
- 保持仓库核心不变：`prepare.py` 只读；训练仍走 `uv run train.py`
- 不引入完整 LLM Agent（那是 Claude/Codex 的事）；本 UI 负责**人机共驾的实验循环**
- 超参优先通过环境变量（`AR_*`）注入，避免破坏 `train.py` 结构
- 可选依赖：`fastapi` / `uvicorn`，不污染默认训练依赖
- 本地单机、单用户，无登录

### 非目标（YAGNI）
- 多用户 / 云端调度 / 分布式多 GPU
- 自动改写 `train.py` 架构代码
- 完整复刻 Claude Agent 自主 overnight 研究

## 架构变更

```
web/
  app.py              — FastAPI：状态、准备、训练进程、git、results、SSE 日志
  loop_engine.py      — 实验循环状态机（idle/running/deciding/…）
  static/             — 前端静态资源（无 Node 构建）
    index.html
    app.css
    app.js
docs/plans/...        — 本需求与计划
pyproject.toml        — optional-dependencies: ui
```

## 实施步骤

### 阶段 1：Loop Engine + API
1. 循环状态机与结果解析
2. REST + SSE：status / prepare / run / stop / decide / results / program / env

### 阶段 2：前端控制台
3. 向导式布局：环境检查 → 研究指引 → 实验旋钮 → 循环面板 → 历史
4. 实时日志、指标卡片、保留/丢弃决策

### 阶段 3：Loop Engineering 打磨
5. 启动服务冒烟、API 自检、文档入口

## 测试策略
- API：status / results / parse metrics 单元级自检
- 集成：启动 uvicorn，`/` 返回 200
- 端到端：用户旅程（不强制真跑满 5 分钟训练）

## 风险与缓解
- **训练过久 / 卡死**：超时杀进程（>10 分钟），UI 可 Stop
- **误操作 git**：仅在 `autoresearch/*` 分支允许 keep/discard；discard 用 soft reset
- **无 GPU**：明确展示 device，提供 macOS 小配置预设

## 成功标准
- [x] `uv run --extra ui python -m web.app` 可启动
- [x] 浏览器可完成：看状态 → 改指引/超参 → 开跑/演示 → 看日志 → 记结果
- [x] 循环状态可观测、可停止
- [x] 演示模式可练习 keep/discard（无需真训练）
