# AutoResearch 控制台（小白前端）

本地 Web UI，把 `program.md` 里的实验循环变成可视化操作台。

## 安装

```bash
uv sync --extra ui
```

## 启动

```bash
uv run --extra ui python -m web.app
```

浏览器打开：http://127.0.0.1:8765

## 能做什么

1. 查看设备 / 数据 / git 分支状态  
2. 一键创建 `autoresearch/<tag>` 分支；可用「环境准备」按本机 GPU/macOS/CPU 安装依赖并冒烟检查  
3. 运行 `prepare.py`  
4. 按平台编辑研究指引：GPU / macOS / CPU × 中英；启动时会**自动感知本机设备**并选择对应预设与指引  
5. 用预设或实验参数设置 `AR_*` 环境变量（不必手改代码）；也可点「跟随本机自动选择」重新同步  
6. 启动 / 停止训练，实时看日志与 **loss 收敛曲线**；或点「演示一轮」练习 keep/discard  
7. 根据 `val_bpb` 选择 **keep / discard / crash**，写入 `results.tsv`，并在历史图中看趋势  

在 Mac / CPU 上会默认套用缩小预设；若手动改过预设，点「跟随本机自动选择」可恢复自动模式。

## Loop Engineering

控制台按状态机推进：`idle → preparing/running → deciding → idle`，并记录 checkpoints，支持随时 Stop。

完整需求见：`docs/plans/2026-07-12-autoresearch-ui-requirements.md`
