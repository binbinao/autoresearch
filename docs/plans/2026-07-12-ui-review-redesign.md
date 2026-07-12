# UI Review：AutoResearch Console

依据：ECC `frontend-design` 审美原则 + Vercel Web Interface Guidelines。

## 主要问题

### 信息架构
- `index.html` 首屏 92vh 营销 Hero，小白要做实验却先滚很长 — 控制台应「打开即工作」
- 5 个始终展开的长 section（环境 / 指引 / 旋钮 / 循环 / 历史）同级竞争，主路径被淹没
- 历史表与历史图重复；Checkpoints 与 status message 重复

### 视觉
- 全页等权分割线 + mono 正文 → 显得碎、像调试页而非产品
- 按钮行过密（一排 3–4 个同类动作）
- 图表与日志纵向堆叠，首屏看不到决策区

### 可访问性（Guidelines）
- `app.css` 输入 focus 无 `:focus-visible` 环替代方案不足
- 缺 `color-scheme`、`prefers-reduced-motion`
- 缺 skip link；部分按钮无明确主次层级文案

## 设计方向（执行）

**Industrial paper workbench（精简仪器台）**
- 浅色纸感底 + 深墨字 + 单一青绿点缀（避免紫/奶油衬线套路）
- 顶栏：品牌 + 最佳 val_bpb + 状态条
- 主舞台：跑实验 + 双图 + 决策（一屏完成）
- 次要：Setup / 指引 / 旋钮 用 `<details>` 折叠
- 日志默认折叠；历史表紧凑跟在图下

## 成功标准
- [x] 首屏可见：状态、开跑、图表
- [x] 次要配置默认折叠（指引 / 旋钮 / 日志）
- [x] 浅色工作台 + 青绿点缀，焦点可见，支持 reduced-motion
