# FEAT-003：回测适配层

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见 [FEAT-030/06-app-layout.md](../FEAT-030-因子回测流程重构/06-app-layout.md) 与 [ADR-029](../../05-技术决策/ADR-029-研究服务采用services与models分层.md)。FEAT-029 因子来源加载目标保持不变。


> 范围演进已实施：[FEAT-030](../FEAT-030-因子回测流程重构/README.md) 已使因子回测退出本适配层，
> 组合职责归 PortfolioEngine，收益和净值归 MetricEngine，由应用层 BacktestEngine 编排。
> 策略回测仍使用本适配层，本 Feature 的已交付状态不变。

- 状态：已完成
- 所属 Initiative：INIT-001 投研核心
- 所属能力：策略回测
- 代码位置：`QuantCore/quantcore/backtest/adapter/`

## 目标

通过统一契约为策略回测接入 NativeEngine；因子回测现由应用层 BacktestEngine 组织
PortfolioEngine 与 MetricEngine，不再把本适配层作为因子主链。

## 文档索引

- `03-technical-design.md`：适配层详细设计和使用方式。

## 文档缺口

该 Feature 在新工作流建立前已完成，Proposal、Requirements、Project Plan 和 Verification 后续按需要补录。
