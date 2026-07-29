# FEAT-017：策略资产目录与版本化持久化

- 状态：待验收
- 所属 Initiative：INIT-001 投研核心
- 所属能力：策略研究、研究基础设施
- 宏观影响：L1（补齐既有策略研究闭环，不改变产品模块边界）

## 目标

将项目级策略源码以 `.py + index.yaml` 的形式持久化，并让向量化策略回测可精确引用已保存的策略版本。

## 文档索引

- `01-feature-proposal.md`：价值、竞品输入与 MVP 边界
- `02-product-requirements.md`：用户流程、业务规则与验收标准
- `03-technical-design.md`：目录、接口、兼容、测试与回滚设计
- `04-project-plan.md`：任务、排期、风险和里程碑
- `05-verification.md`：验收与测试记录
