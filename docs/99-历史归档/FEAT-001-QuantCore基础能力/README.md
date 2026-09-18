# FEAT-001：QuantCore 核心基础设施

> **已废弃归档（2026-09-02）**：QuantCore 独立共享库定位已由 ADR-029 取消，
> 本包全部设计仅作历史追溯，不构成任何当前约束。现行架构见
> [FEAT-030 因子回测流程重构](../../03-功能文档/FEAT-030-因子回测流程重构/README.md) 与
> [ADR-029](../../05-技术决策/ADR-029-研究服务采用services与models分层.md)。

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/README.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> 已批准实施：[FEAT-030 因子回测流程重构](../../03-功能文档/FEAT-030-因子回测流程重构/README.md) 已在 QuantCore 增加
> PortfolioEngine，并调整 Data/Factor/Metric 的职责；完整 BacktestEngine 位于应用层。
> 本 Feature 的基础版状态不变，FEAT-030 主链已实施，专项验收中。

- 状态：已完成（基础版）
- 所属 Initiative：INIT-001 投研核心
- 所属能力：数据、因子研究、策略回测、绩效指标
- 代码位置：`QuantCore/quantcore/`

## 文档索引

- `01-feature-proposal.md`：功能背景和范围
- `02-architecture.md`：模块架构
- `03-modules.md`：模块职责
- `04-class-design.md`：类设计
- `05-runtime-flow.md`：运行流程

## 文档缺口

该 Feature 在新工作流建立前已实现，尚需补充正式 Project Plan 和 Verification，后续重要变更应拆分为新的 Feature。
