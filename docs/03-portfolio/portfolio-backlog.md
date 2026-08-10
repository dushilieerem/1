# Portfolio Backlog

> Initiative 和 Feature 的统一状态入口。状态定义见 `../01-workflow/文档更新规则.md`。

## Initiatives

| ID | 名称 | 优先级 | 状态 | 目标阶段 | 说明 |
|----|------|--------|------|----------|------|
| INIT-001 | 投研核心 | P0 | 开发中 | Wave 1 | QuantCore + ResearchEngine 最小研究闭环 |
| INIT-002 | 交易执行 | P1 | 待分析 | Wave 2 | 模拟盘、组合风控与实盘执行 |
| INIT-003 | 用户、社区与 AI SaaS 平台 | P1 | 待分析 | Wave 3 | 用户、权限、资产隔离、社区、AI、Web 与商业化能力 |
| INIT-004 | 投研能力 Phase 2 | P0 | 待决策 | Wave 1 | 因子预处理、测试和 AI 研究增强 |

## Features

| ID | 名称 | 所属 Initiative | 所属能力 | 优先级 | 状态 |
|----|------|-----------------|----------|--------|------|
| FEAT-001 | QuantCore 核心基础设施 | INIT-001 | 数据/因子/回测/指标 | P0 | 已完成（基础版） |
| FEAT-002 | ResearchEngine 研究服务 | INIT-001 | 策略研究 | P0 | 已完成（基础版 + 因子分析 API 增量） |
| FEAT-003 | 回测适配层 | INIT-001 | 策略回测 | P0 | 已完成 |
| FEAT-004 | 因子资产目录与回测结果缓存 | INIT-001 | 因子研究/研究基础设施 | P0 | 已完成 |
| FEAT-005 | Qlib Alpha158 / Alpha360 特征库 | INIT-001 | 因子研究 | P1 | 已完成 |
| FEAT-006 | 事件驱动策略回测引擎 | INIT-001 | 策略研究/策略回测 | P0 | 开发中（日频内核 MVP） |
| FEAT-008 | 结构化因子组合策略 | INIT-001 | 策略研究/策略回测 | P0 | 已完成 |
| FEAT-009 | 聚宽兼容因子库 | INIT-001 | 因子研究/数据基础设施 | P0 | 开发中（第一批技术因子） |
| FEAT-010 | 投研因子数据底座 | INIT-001 | 数据/因子研究 | P0 | 待批准（数据授权与样本待确认） |
| FEAT-011 | 内置因子库回测 API | INIT-001 | 因子研究/研究 API | P0 | 开发中 |
| FEAT-013 | 机器学习模型接入与预测回测 | INIT-001 | 因子研究/策略研究 | P0 | 待评审 |
| FEAT-014 | 策略调仓日志 | INIT-001 | 策略研究/策略回测 API | P1 | 已完成 |
| FEAT-015 | 个股日线行情 API | INIT-001 | 数据/研究 API | P1 | 开发中 |
| FEAT-016 | AI 自然语言因子生成 API | INIT-004 | AI 研究助手/因子研究 | P0 | 开发中（受控 MVP） |
| FEAT-017 | 策略资产目录与版本化持久化 | INIT-001 | 策略研究/研究基础设施 | P0 | 待验收 |
| FEAT-018 | 自定义证券池与组合基准 | INIT-001 | 数据/因子研究/策略回测 | P1 | 开发中（ResearchEngine 快照契约已完成；WebApp CRUD 待交付） |
| FEAT-019 | AI 自然语言向量化策略生成 API | INIT-004 | AI 研究助手/策略研究 | P0 | 开发中（受控 MVP） |
| FEAT-020 | AI 回测解读与优化建议 | INIT-004 | AI 研究助手/策略研究/因子研究 | P0 | 开发中（受控 MVP） |
| FEAT-021 | 股指与成分股查询 API | INIT-001 | 数据/研究 API | P1 | 已完成 |
| FEAT-022 | 经典策略迁移 | INIT-001 | 策略研究/策略回测 | P1 | 开发中（已覆盖 RSI、CANSLIM Lite、KD、一目均衡表、均线排列、配对交易、Aroon、KST、聂夫、戴维斯双击、12-1 动量、小盘价值、红利低波狗股、三重滤网、抛物线 SAR、Fama-French 多因子、凯特纳通道、Williams %R、德邦特—塞勒长期反转、豪根—海因斯低波动异象、Piotroski F-Score、股息增长、OBV、蔡金、Dual Thrust、净营运资产异象） |
| FEAT-023 | WorldQuant Alpha 101 因子库迁移 | INIT-001 | 因子研究 | P0 | 已完成 |

## 维护要求

- 新 Initiative 或 Feature 获得编号时立即登记。
- 状态变化时同时更新本表与对应 Feature README。
- 标记已完成前必须具备 Verification；历史已交付能力允许标记“已完成（基础版）”并在后续补验收记录。
