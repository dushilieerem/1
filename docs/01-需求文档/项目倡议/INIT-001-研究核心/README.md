# INIT-001：投研核心

- 状态：开发中
- 优先级：P0
- 目标阶段：Wave 1

## 目标

完成数据、因子、策略、回测和分析的最小研究闭环，为 AI 与交易能力提供稳定底座。

## 已纳入 Feature

- `FEAT-001`：QuantCore 核心基础设施
- `FEAT-002`：ResearchEngine 研究服务
- `FEAT-003`：回测适配层
- `FEAT-006`：事件驱动策略回测引擎
- `FEAT-009`：聚宽兼容因子库（开发中；已交付技术、风险与情绪第一批）
- `FEAT-010`：投研因子数据底座（待批准；点时财务、复权、交易状态和市场基准）
- `FEAT-011`：内置因子库回测 API（开发中；内置库完整加载与自定义函数模板并存）
- `FEAT-018`：自定义证券池与组合基准（待决策；统一供因子研究与策略回测引用）
- `FEAT-022`：经典策略迁移（已覆盖 CCI、MFI、TRIX、ROC、Ultimate Oscillator、Vortex Indicator、Relative Vigor Index、Elder Force Index、CMO、Fisher Transform、EOM、VPT、AO、BOP、Choppiness、Coppock、DPO、TSI、StochRSI、RVI、Connors RSI(2)、Supertrend、Hull Moving Average、Williams Alligator、KAMA、McGinley Dynamic、Heikin-Ashi、Pivot Point、BBI、Mass Index、VHF、WVAD、TEMA、SMI、Ulcer Index、STC、Elder Ray、Klinger、RMI、FRAMA 及既有经典策略资产）

2026-08-24 增量：新增 Elder Ray、Klinger、RMI、FRAMA 四个独立事件策略资产；不修改 QuantCore、EventEngine 或 StrategyCatalog 共享实现。
2026-08-25 增量：新增 ARBR、PSY、VR、VROC 四个独立事件策略资产；不修改 QuantCore、EventEngine 或 StrategyCatalog 共享实现。
- `FEAT-023`：WorldQuant Alpha 101 因子库迁移（已完成；独立库 `worldquant_alpha101`）
- `FEAT-026`：国泰君安 Alpha191 因子库迁移（已完成；独立库 `gtja_alpha191`）
- `FEAT-027`：因子批量回测与指标仓库（开发中；异步 CLI、SQLite 标量指标仓库与只读查询）
- `FEAT-029`：数据库因子加载与回测执行器最小改造（开发中；先稳定 FactorEngine/MetricEngine/DataEngine 边界，数据库 loader 后续接入）
- `FEAT-024`：iFinD 宽表规范与渐进替换（已批准；按业务域组织多字段宽表，采用不可变发布与只读内存快照）
- `FEAT-025`：免费数据源补齐日频基本面与证券状态 MVP（待批准；BaoStock + AKShare/CNINFO，内部研究范围）

## 已批准、实施中的架构演进

- 用户确认 [ADR-029](../../../05-技术决策/ADR-029-研究服务采用services与models分层.md)：取消 QuantCore
  独立共享库定位，五个 Engine 的逻辑进入 services、内部数据结构进入 models，数据访问进入 database。
  仅 ResearchEngine 拥有这些实现；不为尚不存在的 TradingEngine 设计共享包。

- [FEAT-030：因子回测流程重构](../../../03-功能文档/FEAT-030-因子回测流程重构/README.md)：P0，主链已实施，M5 专项验收中。
- BacktestEngine 组织完整因子流程，Data/Factor/Portfolio/Metric 分别负责数据与筛选、因子加工、组合及效果计算。
- 本期不迁移策略或因子数据库，不改 WebApp；不改变 Wave 1 业务范围和当前已交付状态。
- FEAT-029 保留因子来源加载目标，其原阶段执行器设计已由 FEAT-030 的 BacktestEngine 主链接替。

## 文档

- [业务层领域设计](domain-design.md)：研究核心领域设计。
