# FEAT-028：ResearchEngine 分层应用架构

- 状态：开发中
- 所属 Initiative：INIT-001 投研核心
- 优先级：P0

## 目标

将 QuantCore、ResearchEngine、Factor 和 Strategy 的运行时统一迁移到
`ResearchEngine/app`，以 `app.*` 作为唯一 Python 命名空间，并以
`app.main` 作为 FastAPI 唯一正式入口。

本次是一次性破坏性包迁移：不保留旧的 `quantcore.*`、`researchengine.*` 转发层，
不修改 WebApp。HTTP 契约统一使用 `/api`，WebApp 适配另行安排。

## 文档索引

- `01-feature-proposal.md`：背景、用户价值、MVP 范围
- `02-product-requirements.md`：用户故事、边界和验收标准
- `03-technical-design.md`：分层、依赖、运行时和迁移设计
- `04-project-plan.md`：任务、风险、排期和里程碑
- `05-verification.md`：验证矩阵与交付门槛
