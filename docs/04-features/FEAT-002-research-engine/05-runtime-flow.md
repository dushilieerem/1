# ResearchEngine 运行流程图

> 文档版本：v2.1
> 最后更新：2026-08-18
> 关联：`02-architecture.md`（状态与扩展）、`04-class-design.md`（类设计）

---

## 1. 整体流程（Manager 管理执行资源）

```
┌─────────────────────────────────────────────────────────────────┐
│  前端 / AI Agent                                                 │
│  - 管理因子库、策略库                                              │
│  - 组装因子代码 + 参数                                            │
│  - 调用 ResearchEngine API                                        │
│  - 处理结果                                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ POST /api/backtest/factor 或 /api/backtest/strategy
                           │ { factor_code, factor_name,
                           │   universe, start, end, params }
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  ResearchEngine 实例（任意节点）                                    │
│                                                                  │
│  FastAPI 路由 → ExperimentManager.submit()                       │
│       ① 生成任务键、检查缓存/同键进行中的任务                     │
│       ② 有界排队，等待 Manager 自有线程池                          │
│       ③ 工作线程执行一次因子/策略回测                              │
│       ④ 回传 Future 结果或异步接口的 run_id                        │
│                                                                  │
│  单次回测执行单元                                                   │
│  ① 编译因子代码（exec → FactorLibrary）                             │
│  ② 初始化 QuantCore 引擎                                          │
│  ③ 取完整历史 Panel 并计算因子                                    │
│  ④ 裁剪 start/end 收益确认区间                                  │
│  ⑤ 构建策略、计算净值/收益/持仓/指标                               │
│  ⑥ 序列化为 FactorBacktestResponse 或 StrategyBacktestResponse   │
│                                                                  │
│  Manager 的任务状态只在当前进程内有效                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 200 + JSON
                           │ { metrics, equity_curve, ... }
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  前端处理结果                                                      │
│  - 显示收益曲线、指标                                              │
│  - 决定是否存储到数据库                                            │
│  - 传递给 AI Agent 进行分析                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Manager 与单次回测详细流程

```
请求到达 FastAPI
  │
  ▼
Step 1  ExperimentManager 接收任务
         规范化请求 → 计算任务键 → 检查缓存和 inflight 任务
         已有相同任务 → 复用 Future
         无空闲容量 → 返回 HTTP 429
  │
  ▼
Step 2  Manager 有界排队
         状态：QUEUED
         不使用 FastAPI/AnyIO 通用线程池执行回测
  │
  ▼
Step 3  Manager 工作线程开始执行
         状态：RUNNING
  │
  ▼
Step 4  编译因子代码
         exec(factor_code) → FactorLibrary 子类实例化
          → factor = getattr(library, factor_name)
         如果编译失败 → 返回 { error: "语法错误: ..." } HTTP 200
  │
  ▼
Step 5  初始化 QuantCore 引擎
         data_dir = req.data_dir | env.SVQUANT_DATA_DIR | /data/market
         data_provider = FieldParquetProvider(data_dir)
         data_engine = DataEngine(provider=data_provider)
         factor_engine = FactorEngine(compute_backend="python")
         metric_engine = MetricEngine()
  │
  ▼
Step 6  取面板数据
         calculation_panels = data_engine.get_panels(None, None)
          → 完整历史 Panel(open, high, low, close, volume, total_mv, ...)
         evaluation_close = calculation_panels["close"].loc[start:end]
         evaluation_start = evaluation_close.index[0]
          → 用收益确认区间首个实际交易日解析 universe
         universe_data = resolve_universe(data_engine, universe, as_of=evaluation_start)
  │
  ▼
Step 7  计算因子值
         all_factor_values = factor_engine.compute_panel(factor.name, calculation_panels)
          → 使用完整历史，自动覆盖 rolling/pct_change 等预热
         factor_values = all_factor_values.loc[start:end]
          → 仅将收益确认区间交给回测和分析
  │
  ▼
Step 8  计算远期收益（IC 用）
         fwd_returns = forward_returns(close_panel, horizon=ic_horizon)
  │
  ▼
Step 9  构建策略 → 回测适配器
         strategy = FactorQuantileStrategy(
             factor_values, close_panel,
             rebalance=params.rebalance,
             stock_num=params.stock_num,
             long_short=params.long_short
         )
         signals = strategy.generate_signals()
         
         engine_name = "native"
         config = BacktestConfig(
             engine=engine_name,
             initial_capital=params.initial_capital,
             commission_rate=params.commission_rate,
             slippage_rate=params.slippage_rate,
         )
         bt_engine = get_backtest_engine(engine_name)
         bt_result = bt_engine.run(signals, config)
          → equity_curve, returns, positions
  │
  ▼
Step 10 计算指标
         context = MetricContext(
             equity=bt_result.equity_curve,
             returns=bt_result.returns,
             factor_values=factor_values,
             forward_returns=fwd_returns,
             positions=bt_result.positions,
             periods_per_year=252
         )
         metrics = metric_engine.calculate_all(context)
          → annual_return, sharpe, sortino, calmar,
            max_drawdown, volatility, ic, rank_ic,
            win_rate, turnover, trade_count
  │
  ▼
Step 11 序列化结果并更新任务状态
         result = BacktestResult(
             metrics=metrics,
             equity_curve=[{date, value} for ...] if include_equity else None,
             date_range={start, end},
             final_equity=equity_curve[-1],
             meta={factor, universe, engine, rebalance, stock_num, long_short},
             chart_png_b64=... if include_chart else None,
             error=None
         )
  │
  ▼
返回 Response → Future 完成 → 同步 HTTP 200，或 GET /api/experiments/{run_id} 查询
```

---

## 3. 回测适配器内部（Step 6 展开）

```
FactorQuantileStrategy.generate_signals(panel) → BacktestSignals(target_weights)
                         │
                         ▼
              IBacktestEngine.run(signals, config)
              ┌──────────────┴──────────────┐
              ▼                              ▼
        NativeEngine（自研向量化，默认，
          与 build_factor_portfolio 逐位等价）
              │                              │
              └──────────────┬───────────────┘
                             ▼
              BacktestResult(equity_curve, returns, positions)
```

---

## 4. HTTP API 时序

```
前端                     FastAPI 路由              ExperimentManager
  │                           │                           │
  │ POST /api/backtest/factor │                           │
  │ { factor_code,            │                           │
  │   factor_name,            │                           │
  │   universe,               │                           │
  │   params }                │                           │
  │──────────────────────────►│                           │
  │                           │ submit_factor_backtest()  │
  │                           │──────────────────────────►│
  │                           │                           │
  │                           │                           │ QUEUED/RUNNING
  │                           │                           │ → Experiment.run()
  │                           │                           │ → QuantCore
  │                           │                           │ → Future 完成
  │                           │                           │
  │ 200 + JSON                │                           │
  │ { metrics,                │                           │
  │   equity_curve,           │                           │
  │   final_equity,           │                           │
  │   meta,                   │                           │
  │   error }                 │                           │
  │◄──────────────────────────│                           │
  │                           │                           │
```

---

## 5. 多实例部署流程

```
                        负载均衡器
                   （Nginx / K8s Service）
                   ┌────┴────┐────┐
                   │         │    │
               RE-1        RE-2   RE-N
                   │         │    │
                   └────┬────┘────┘
                        │
         每个进程：一个 FastAPI + 一个 ExperimentManager
                        │
              共享只读存储（MarketData）
                   ┌────┴────┐
                   │         │
              stock_daily/  fundamentals/
```

- 每个实例独立处理请求，每个实例内由 Manager 限制回测并发
- 默认每个 Uvicorn worker 2 个回测线程、8 个排队位
- 实例间无任务状态共享；多实例异步查询需要外部 RunStore
- 数据从共享只读存储读取
- 任意实例可以处理任意请求

---

## 6. 关键设计要点

| 要点 | 说明 |
|------|------|
| **状态边界** | 单次回测独立；Manager 的任务状态和线程池只在当前进程内存在 |
| **代码编译** | 因子代码通过 `exec()` 编译执行，不依赖本地因子文件 |
| **所有参数通过请求传入** | 不依赖本地 config.yaml |
| **结果不持久化** | 结果序列化后返回前端，由前端决定存储策略 |
| **水平扩展** | 多实例部署可行，但每个 worker 会独立拥有 Manager 和并发额度 |
| **错误不抛 500** | 因子代码错误 → `error` 字段填充，HTTP 200 返回 |
| **回测经适配器** | `IBacktestEngine` 契约，统一由 native 执行 |
| **指标在 MetricEngine** | Runner 不算指标，委托 QuantCore MetricEngine |
| **HTTP 是薄层** | `researchengine.api` 只提交 Manager，不新增回测逻辑 |
| **QuantCore 无感** | ResearchEngine 只调用 QuantCore，不关心其内部实现 |
