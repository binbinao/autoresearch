# 实施方案补充：训练进程图示化

## 概述

在现有 AutoResearch 控制台中增加图示：实时展示本轮训练 loss 收敛曲线，并展示跨实验的 `val_bpb` 历史趋势，让小白直观判断「是否在学」与「是否比以前更好」。

## 需求分析（ECC）

### 用户与目标
- **用户**：同一批小白用户，已能跑循环，但读滚动日志吃力
- **目标**：一眼看到训练是否收敛、历史实验指标走势
- **成功标准**：
  - 训练进行中，loss–step 曲线随日志实时更新
  - 历史区有 val_bpb 折线/点图（区分 keep/discard）
  - 无新前端构建链、尽量不增加依赖（Canvas 自绘）
  - 演示模式也产出可看的合成曲线

### 假设与约束
- 训练日志格式来自 `train.py` 的 `\rstep … | loss: …` 行
- 后端解析序列，经 `/api/status` 下发；前端只负责渲染
- 仍在分支 `autoresearch/jul12` 上改 `web/`

### 非目标
- 完整 TensorBoard / 多 run 对比平台
- 服务端持久化每步曲线到磁盘（会话内内存即可）

## 架构变更
- `web/loop_engine.py`：解析 progress 点；status 增加 `progress_series`
- `web/static/*`：新增双图（本轮收敛 + 历史 val_bpb）
- `web/test_loop_engine.py`：解析用例

## 成功标准
- [x] 解析 step/loss 单测通过
- [x] status 含 progress_series
- [x] UI 两块图可见且随 refresh 更新
- [x] 演示模式产出合成收敛曲线
