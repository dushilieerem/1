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
- `FEAT-022`：经典策略迁移（已覆盖 CCI、MFI、TRIX、ROC、Ultimate Oscillator、Vortex Indicator、Relative Vigor Index、Elder Force Index、CMO、Fisher Transform、EOM、VPT 及既有经典策略资产）
- `FEAT-023`：WorldQuant Alpha 101 因子库迁移（已完成；独立库 `worldquant_alpha101`）
- `FEAT-024`：iFinD 宽表规范与渐进替换（已批准；按业务域组织多字段宽表，采用不可变发布与只读内存快照）

## 文档

- `domain-design.md`：研究核心领域设计。
