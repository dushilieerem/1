# FEAT-018：自定义证券池与组合基准

- 状态：开发中（ResearchEngine 快照契约已完成；WebApp CRUD 待交付）
- 所属 Initiative：INIT-001 投研核心
- 所属能力：数据、因子研究、策略回测
- 宏观影响：L1（在既有研究能力中补充可复用研究资产，不改变产品模块边界）

## 目标

让研究员将自定义的股票集合和可复现的比较组合保存为版本化资产，并在因子与策略回测中按 ID 引用。股票池决定研究截面与可交易范围；组合基准决定绩效比较口径，两者不能互相替代。

## 文档索引

- `01-feature-proposal.md`：价值、竞品输入与 MVP 边界。
- `02-product-requirements.md`：用户流程、业务规则和验收标准。
- `03-technical-design.md`：资产模型、接口、数据影响和测试策略。
- `04-project-plan.md`：任务、排期、风险和里程碑。
- `05-verification.md`：验收标准、自动化验证和已知限制。

## 当前结论

WebApp 负责用户资产的 CRUD、鉴权、数据库存储、版本解析和快照生成；ResearchEngine 只校验并消费快照。历史逐日成分、规则选股和事件驱动接入作为后续增量。现有固定指数代码继续兼容。

## API 摘要

- `POST /api/backtest/factor`、`POST /api/backtest/strategy`：使用
  `universe_snapshot` 和 `benchmark_snapshot` 接收 WebApp 已解析的资产快照。
  各引用不能与旧的 `universe`、`benchmark` 参数同时传入。
