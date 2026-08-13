# ResearchEngine 运行流程图

> 文档版本：v2.0
> 最后更新：2026-07-15
> 关联：`02-architecture.md`（无状态设计）、`04-class-design.md`（类设计）

---

## 1. 整体流程（无状态设计）

```
┌─────────────────────────────────────────────────────────────────┐
│  前端 / AI Agent                                                 │
│  - 管理因子库、策略库                                              │
│  - 组装因子代码 + 参数                                            │
│  - 调用 ResearchEngine API                                        │
│  - 处理结果                                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ POST /api/backtest
                           │ { factor_code, factor_name,
                           │   universe, start, end, params }
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  ResearchEngine 实例（任意节点）                                    │
│                                                                  │
│  BacktestRunner.run()                                            │
│  ① 编译因子代码（exec → FactorLibrary）                             │
│  ② 初始化 QuantCore 引擎                                          │
│  ③ data_engine.get_panels(完整历史) → Panel                        │
│  ④ factor_engine.compute_panel → 完整历史 factor_values            │
│  ⑤ 裁剪 start/end 收益确认区间                                  │
│  ⑥ FactorQuantileStrategy → signals                              │
│  ⑦ get_backtest_engine.run() → equity/returns/positions          │
│  ⑧ MetricEngine.calculate_all() → metrics                        │
│  ⑨ 序列化 → BacktestResult                                       │
│                                                                  │
│  实例间无共享状态，每个请求独立执行                                    │
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

## 2. BacktestRunner.run() 详细流程

```
请求到达
  │
  ▼
Step 1  编译因子代码
         exec(factor_code) → FactorLibrary 子类实例化
          → factor = getattr(library, factor_name)
         如果编译失败 → 返回 { error: "语法错误: ..." } HTTP 200
  │
  ▼
Step 2  初始化 QuantCore 引擎
         data_dir = req.data_dir | env.SVQUANT_DATA_DIR | /data/market
         data_provider = FieldParquetProvider(data_dir)
         data_engine = DataEngine(provider=data_provider)
         factor_engine = FactorEngine(compute_backend="python")
         metric_engine = MetricEngine()
  │
  ▼
Step 3  取面板数据
         calculation_panels = data_engine.get_panels(None, None)
          → 完整历史 Panel(open, high, low, close, volume, total_mv, ...)
         evaluation_close = calculation_panels["close"].loc[start:end]
         evaluation_start = evaluation_close.index[0]
          → 用收益确认区间首个实际交易日解析 universe
         universe_data = resolve_universe(data_engine, universe, as_of=evaluation_start)
  │
  ▼
Step 4  计算因子值
         all_factor_values = factor_engine.compute_panel(factor.name, calculation_panels)
          → 使用完整历史，自动覆盖 rolling/pct_change 等预热
         factor_values = all_factor_values.loc[start:end]
          → 仅将收益确认区间交给回测和分析
  │
  ▼
Step 5  计算远期收益（IC 用）
         fwd_returns = forward_returns(close_panel, horizon=ic_horizon)
  │
  ▼
Step 6  构建策略 → 回测适配器
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
Step 7  计算指标
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
Step 8  序列化结果
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
返回 BacktestResult → 序列化为 JSON → HTTP 200
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
前端                     FastAPI 路由                 BacktestRunner
  │                           │                           │
  │ POST /api/backtest        │                           │
  │ { factor_code,            │                           │
  │   factor_name,            │                           │
  │   universe,               │                           │
  │   params }                │                           │
  │──────────────────────────►│                           │
  │                           │ run_backtest_from_code()  │
  │                           │──────────────────────────►│
  │                           │                           │
  │                           │  ① 编译因子代码            │
  │                           │  ② 初始化 QuantCore       │
  │                           │  ③ 取面板 + 算因子         │
  │                           │  ④ 跑回测（Native）        │
  │                           │  ⑤ 算指标                 │
  │                           │  ⑥ 序列化结果              │
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
              共享只读存储（MarketData）
                   ┌────┴────┐
                   │         │
              stock_daily/  fundamentals/
```

- 每个实例独立处理请求
- 实例间无通信（shared-nothing）
- 数据从共享只读存储读取
- 任意实例可以处理任意请求

---

## 6. 关键设计要点

| 要点 | 说明 |
|------|------|
| **无状态** | 每个请求独立编译因子代码、独立初始化引擎、独立执行回测 |
| **代码编译** | 因子代码通过 `exec()` 编译执行，不依赖本地因子文件 |
| **所有参数通过请求传入** | 不依赖本地 config.yaml |
| **结果不持久化** | 结果序列化后返回前端，由前端决定存储策略 |
| **水平扩展** | 多实例部署，负载均衡分发，shared-nothing |
| **错误不抛 500** | 因子代码错误 → `error` 字段填充，HTTP 200 返回 |
| **回测经适配器** | `IBacktestEngine` 契约，统一由 native 执行 |
| **指标在 MetricEngine** | Runner 不算指标，委托 QuantCore MetricEngine |
| **HTTP 是薄层** | `researchengine.api` 只调 BacktestRunner，不新增回测逻辑 |
| **QuantCore 无感** | ResearchEngine 只调用 QuantCore，不关心其内部实现 |
