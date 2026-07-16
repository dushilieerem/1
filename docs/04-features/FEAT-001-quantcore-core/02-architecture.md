# 整体结构

```
┌──────────────────────────────────┐
│   SVQuant 界面 / 前端              │   ← 阶段三 Web / AI 平台
└──────────────┬───────────────────┘
               │  HTTP（FastAPI）
               ▼
┌──────────────────────────────────┐
│   researchengine.api             │   ← HTTP 适配层（/api/backtest 等）
└──────────────┬───────────────────┘
               │  调 SDK
               ▼
┌──────────────────────────────────┐
│   ResearchEngine                 │   ← 用户入口
│   Experiment / ExperimentManager │
└──────────────┬───────────────────┘
               │  调用
               ▼
┌──────────────────────────────────┐
│   QuantCore                      │   ← 底层引擎
│   data / factor / metric         │
│   backtest/adapter（Native|VectorBT）│
└──────────────┬───────────────────┘
               │
   Historical Feed / Live Feed
```

ResearchEngine 永远是用户入口。

QuantCore 永远是底层引擎。

`backtest/adapter` 是可插拔回测后端（Native / VectorBT），ResearchEngine 经 `IBacktestEngine`
契约按 config 切换。详见 `../FEAT-003-backtest-adapter/03-technical-design.md`、`../FEAT-002-research-engine/06-research-api.md`。
