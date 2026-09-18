# 整体结构

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/README.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> FEAT-030 当前实现：应用层 BacktestEngine 编排 QuantCore 的 DataEngine、FactorEngine、
> PortfolioEngine、MetricEngine。数据/筛选、因子加工、组合、效果计算分别归属四引擎。
> [设计与验收](../FEAT-030-因子回测流程重构/README.md) 仍是跨模块约束；下文保留基础版阶段结构，
> 不应据此把完整流程引擎放入 QuantCore。

```
┌──────────────────────────────────┐
│   SVQuant 界面 / 前端              │   ← 阶段三 Web / AI 平台
└──────────────┬───────────────────┘
               │  HTTP（FastAPI）
               ▼
┌──────────────────────────────────┐
│   app.main / app.api.routes      │   ← HTTP 适配层（/api 等）
└──────────────┬───────────────────┘
               │  调 SDK
               ▼
┌──────────────────────────────────┐
│   app.services                   │   ← 用户入口
│   Experiment / ExperimentManager │
└──────────────┬───────────────────┘
               │  调用
               ▼
┌──────────────────────────────────┐
│   app.quantcore                  │   ← 底层引擎
│   data / factor / metric         │
│   backtest/adapter（策略 Native/Event） │
└──────────────┬───────────────────┘
               │
   Historical Feed / Live Feed
```

`app.main` 永远是 HTTP 用户入口，`app.services` 提供 Python 业务入口。

`app.quantcore` 永远是底层引擎，不能依赖 FastAPI 或应用业务层。

`backtest/adapter` 为策略回测提供 Native/Event 后端；因子新主链由应用层 BacktestEngine
直接组织四个 QuantCore 引擎，不经过 `IBacktestEngine`。详见 `../FEAT-003-回测适配层/03-technical-design.md`、
`../../../ResearchEngine/docs/03-功能文档/FEAT-002-研究引擎/06-research-api.md`。
