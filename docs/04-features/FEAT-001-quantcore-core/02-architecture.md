# 整体结构

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
│   backtest/adapter（NativeEngine） │
└──────────────┬───────────────────┘
               │
   Historical Feed / Live Feed
```

`app.main` 永远是 HTTP 用户入口，`app.services` 提供 Python 业务入口。

`app.quantcore` 永远是底层引擎，不能依赖 FastAPI 或应用业务层。

`backtest/adapter` 提供 NativeEngine 回测后端，ResearchEngine 经 `IBacktestEngine`
契约按 config 切换。详见 `../FEAT-003-backtest-adapter/03-technical-design.md`、`../FEAT-002-research-engine/06-research-api.md`。
