# FEAT-026：国泰君安 Alpha191 因子库迁移

- 状态：已完成
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究
- 优先级：P0
- 代码位置：`Factor/libraries/gtja_alpha191.py`

## 目标

将公开的国泰君安 Alpha191 公式以 SVQuant 原生 `FactorLibrary` 提供，支持统一宽表
计算、因子枚举、索引/API 发现和研究回测调用。

## 文档索引

- `01-feature-proposal.md`：背景、价值、竞品与 MVP 范围。
- `02-product-requirements.md`：用户故事、边界与验收标准。
- `03-technical-design.md`：算子、字段契约、兼容与回滚设计。
- `04-project-plan.md`：任务、依赖、风险与里程碑。
- `05-verification.md`：自动化验证记录与未覆盖项。
