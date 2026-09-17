# FEAT-030：因子回测流程重构

- 状态：开发中（services/models 结构迁移完成，原专项验收尚未全部关闭）
- 文档日期：2026-08-28
- 所属 Initiative：INIT-001 投研核心
- 所属能力：ResearchEngine 因子研究
- 优先级：P0（建议）
- 当前交付：四引擎主链及 services/models 目录修订已实现；本轮全量回归 528 passed，见 Verification
- 代码开工条件：已由用户明确批准；代码重构已开始

## 目标

2026-08-28 用户明确取消 QuantCore 独立边界，采用
`main.py / api / models / schemas / services / database / utils / config.py`。
五个 Engine 的业务逻辑进入 services，内部数据结构进入 models；不新增 domain/application/infrastructure。
本次修订以 [目录与职责设计](06-app-layout.md) 和 [ADR-029](../../05-技术决策/ADR-029-研究服务采用services与models分层.md) 为准。
用户已明确授权按该结构实施，原有业务公式、HTTP 和数据库边界不变。

DataEngine 管数据与筛选条件，FactorEngine 管因子加工，PortfolioEngine 管组合，
MetricEngine 管效果计算，BacktestEngine 组织完整流程。

```text
ExperimentManager
  → FactorBacktestExperiment
    → BacktestEngine.run(spec, context)
      → DataEngine：完整行情、股票池、筛选掩码
      → FactorEngine：因子计算、可选预处理
      → PortfolioEngine：分组、权重、持仓、评价数据对齐
      → MetricEngine：收益、净值、基准、指标和扩展分析
      → 汇总 FactorBacktestResult
```

当前因子主链已按此图实现。`FactorBacktestExperiment` 位于
`app.services.factor.experiment`，标准单次、批量和 Python 入口直接进入 `BacktestEngine`；策略回测仍使用自己的 Native/Event
组件。只保留一个具体 BacktestEngine，不增加接口继承、后端注册表或模拟器层。
Manager 和 Experiment 的原有职责保持。

## 已确认范围

- 只重构因子回测；策略回测仍依赖的 NativeEngine、EventBacktestEngine 及信号契约暂时保留。
- 首期迁移停牌/涨停过滤、去极值、标准化，所有入口默认关闭，支持分别显式开启。
- 后续再考虑跌停、北交所、上市不足 180 天过滤及中性化；首期不提供占位参数或空实现。
- 保留现有收益、净值、分组指标公式及展示时序。
- 过滤缺少状态数据时跳过并显式告警；保留在当次结果、缓存和日志，不增加批量历史数据库字段。
- 不修改 WebApp，不迁移因子数据库，不清理历史数据，不处理无关重构。

## 审核顺序与材料

| 顺序 | 材料 | 审核重点 |
|---|---|---|
| 1 | [Feature Proposal](01-feature-proposal.md) | 为什么做、用户和商业价值、范围及资源 |
| 2 | [Product Requirements](02-product-requirements.md) | 默认行为、异常、跨入口一致性、验收标准 |
| 3 | [Technical Design](03-technical-design.md) | 五个引擎职责、输入输出、时序、兼容及迁移 |
| 4 | [Project Plan](04-project-plan.md) | 任务、依赖、人天、风险、里程碑 |
| 5 | [Verification](05-verification.md) | 基线记录与尚未执行的重构验收矩阵 |
| 6 | [ADR-028](../../05-技术决策/ADR-028-因子回测由BacktestEngine编排四引擎.md) | 已采纳；其中包归属由 ADR-029 修订 |
| 7 | [目录与职责修订](06-app-layout.md) | QuantCore 取消，services/models/database 的职责与生命周期 |

## 审核关卡

交付顺序固定为：计划 → 文档落盘 → 用户审核 → 代码重构 → 验收。

- [x] 完成方案讨论及范围确认。
- [x] 编写完整 Feature 文档与拟议 ADR。
- [x] 用户审核通过 Proposal、Requirements、Technical Design、Project Plan。
- [x] 用户明确批准开始 M1–M5 代码重构，满足 Definition of Ready。
- [ ] 完成专项实现、跨入口、并发及数值验收。
- [ ] 更新当前实现基线并标记交付状态。

本次代码开工已获明确授权；当前仍未达到 Feature 最终交付状态，M5 验收完成前不标记为已完成。

## 关联文档

- [Portfolio Backlog](../../01-需求文档/项目组合/portfolio-backlog.md)
- [INIT-001](../../01-需求文档/项目倡议/INIT-001-研究核心/README.md)
- [当前 ResearchEngine 架构](../../../ResearchEngine/docs/02-架构文档/researchengine_architecture.md)
- [ADR-025：现有单一应用执行管线](../../../ResearchEngine/docs/05-技术决策/ADR-025-回测采用单一应用执行管线与可插拔后端.md)
- [ADR-027：已有三引擎兼容式重构](../../05-技术决策/ADR-027-QuantCore三引擎兼容式重构.md)

本 Feature 的实现全部归 ResearchEngine；为保留现有链接，文档仍在当前目录维护，不另行搬迁文档。
