## QuantCore 运行流程图

> 本文保留基础版运行流程；其中“BacktestEngine（交易模拟）”是旧阶段/策略语义。
> [FEAT-030](../../03-模块详细设计/FEAT-030-因子回测流程重构/README.md) 已将完整因子回测放到应用层 BacktestEngine，
> QuantCore 分别承担数据筛选、因子加工、组合和效果计算，策略旧执行内核暂留。

依据 `04-class-design.md` 中的类设计，绘制 QuantCore 四大引擎的完整运行流程。

---

### 1. 整体架构总览

```
ResearchEngine 调用
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              QuantCore                                   │
│                                                                          │
│  ┌────────────────┐    ┌────────────────┐    ┌──────────────────────┐   │
│  │   DataEngine   │───▶│  FactorEngine  │───▶│  BacktestEngine      │   │
│  │   (数据读取)    │    │  (因子计算)     │    │  (交易模拟)           │   │
│  └────────────────┘    └────────────────┘    └──────────┬───────────┘   │
│                                                         │               │
│                                                         ▼               │
│                                                  ┌────────────────┐   │   │
│                                                  │  MetricEngine  │   │   │
│                                                  │  (指标计算)     │   │   │
│                                                  └────────────────┘   │   │
└─────────────────────────────────────────────────────────────────────────┘
         │
         ▼
  Historical Feed / Live Feed
```

---

### 2. DataEngine 运行流程

负责统一数据读取，通过 `IDataProvider` 接口屏蔽数据源差异。

```
                        ResearchEngine
                              │
                    DataEngine.get_bars()
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│                       DataEngine                           │
│                                                            │
│  set_provider(provider)  →  选择数据源                      │
│                                                            │
│  get_bars(symbol, start, end, fields)                      │
│      └──→ provider.get_bars(symbol, start, end, fields)    │
│                                                            │
│  get_universe(date)                                        │
│      └──→ provider.get_universe(date)                      │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│                   IDataProvider 接口                        │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ CSVData      │  │ ClickHouse   │  │   AkShare        │  │
│  │ Provider     │  │ Provider     │  │   Provider       │  │
│  │              │  │              │  │                  │  │
│  │ 读取本地CSV  │  │ 查询分布式   │  │ A股实时/历史数据 │  │
│  │ 文件         │  │ 数据库       │  │                  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │ Wind         │  │ Parquet      │                        │
│  │ Provider     │  │ Provider     │                        │
│  │              │  │              │                        │
│  │ 万得金融终端 │  │ 列式存储文件  │                        │
│  └──────────────┘  └──────────────┘                        │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
                   返回 DataFrame 给调用方
```

**关键原则：** Research 不知道数据来自哪里，只通过 `IDataProvider` 接口获取数据。

---

### 3. FactorEngine 运行流程

负责因子计算，Research 只写因子逻辑。

```
                      FactorEngine.compute(factor_name, data_provider, ...)
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│                      FactorEngine                          │
│                                                            │
│  ① 从 factors 字典中取出 factor                            │
│     factor = self.factors[factor_name]                     │
│                                                            │
│  ② 从 data_provider 读取所需数据                            │
│     data = data_provider.get_bars(universe, start, end)    │
│                                                            │
│  ③ 选择计算后端                                            │
│     ┌─────────────────────────────────────────────────┐   │
│     │              ComputeBackend                      │   │
│     │                                                  │   │
│     │  Python Backend      Numba Backend               │   │
│     │  │                   │                            │   │
│     │  CPython 原生执行    JIT 编译加速                 │   │
│     │  │                   │                            │   │
│     │  C++ Backend         GPU Backend                  │   │
│     │  │                   │                            │   │
│     │  pybind11 调用       CUDA 并行计算                │   │
│     │  │                   │                            │   │
│     └─────────────────────────────────────────────────┘   │
│                                                            │
│  ④ 执行因子计算                                            │
│     factor_values = backend.execute(factor.compute, data)  │
│                                                            │
│  ⑤ 返回因子值序列                                          │
│     return factor_values  (pd.Series)                      │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
                     返回 pd.Series 给调用方
```

**关键原则：** Research 只写 `factor.compute(data)`，不关心后端和引擎代码。

---

### 4. BacktestEngine 运行流程

负责交易模拟，包含完整的订单到成交链路。

```
                        BacktestEngine.run(strategy_func)
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│                      BacktestEngine                        │
│                                                            │
│  ① 初始化 Portfolio                                        │
│     portfolio = Portfolio(initial_capital)                  │
│                                                            │
│  ② 按时间逐 bar 推进                                       │
│     for bar in bars:                                       │
│         │                                                   │
│         ▼                                                   │
│     ┌─────────────────────────────────────────────────┐    │
│     │  ③ 策略生成订单                                   │    │
│     │  orders = strategy_func(bar, portfolio)           │    │
│     │     │                                              │    │
│     │     ▼                                              │    │
│     │  ④ MatchingEngine 撮合                             │    │
│     │  for order in orders:                              │    │
│     │      fills = matching_engine.match(order, bar)     │    │
│     │         │                                           │    │
│     │         ▼                                           │    │
│     │  ⑤ TransactionCost 计算费用                         │    │
│     │  for fill in fills:                                 │    │
│     │      commission, slippage = cost_model.             │    │
│     │          calculate(order, fill.fill_price)           │    │
│     │      fill.commission = commission                   │    │
│     │      fill.slippage = slippage                       │    │
│     │         │                                           │    │
│     │         ▼                                           │    │
│     │  ⑥ Portfolio 更新持仓                               │    │
│     │  portfolio.update(fill)                             │    │
│     │      cash -= fill_price * qty + commission          │    │
│     │      positions[symbol] += qty                       │    │
│     │                                                     │    │
│     └─────────────────────────────────────────────────┘    │
│                                                            │
│  ⑦ 构建 BacktestResult                                     │
│  result = BacktestResult(                                  │
│      portfolio=portfolio,                                  │
│      orders=all_orders,                                    │
│      fills=all_fills,                                      │
│      equity_curve=equity_curve,                            │
│  )                                                         │
│                                                            │
│  ⑧ 返回结果                                               │
│  return result                                             │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
                     返回 BacktestResult 给调用方
```

#### 4.1 撮合流程

```
MatchingEngine.match(order, bars)
      │
      ▼
┌─────────────────────────────────────┐
│  根据 order.order_type 判断          │
│                                      │
│  market order:                       │
│    └── 以当前 bar 的 close 成交       │
│                                      │
│  limit order:                        │
│    └── 比较 order.price 与 bar 价格   │
│        ├── 达到价格 → 成交            │
│        └── 未达到 → 挂单 / 取消       │
│                                      │
│  返回 Fill[]                          │
└─────────────────────────────────────┘
```

**关键原则：** BacktestEngine 只做交易模拟，不计算任何指标（如 Sharpe、IC 等）。

---

### 5. MetricEngine 运行流程

负责所有指标的统一计算，是整个 QuantCore 的"非常重要"模块。

```
                    MetricEngine.calculate(metric_names, data)
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│                      MetricEngine                          │
│                                                            │
│  ① 遍历请求的指标名称                                      │
│  for name in metric_names:                                 │
│      │                                                     │
│      ▼                                                     │
│  ② 从 metrics 字典取出对应指标                              │
│  metric = self.metrics[name]                               │
│      │                                                     │
│      ▼                                                     │
│  ③ 调用指标计算                                            │
│  value = metric.calculate(data)                            │
│      │                                                     │
│      ▼                                                     │
│  ④ 收集结果                                                │
│  result[name] = value                                      │
│                                                            │
│  ⑤ 返回结果字典                                            │
│  return result                                              │
└───────────────────────────────────────────────────────────┘
                              │
                              ▼
                     返回 Dict[str, float] 给调用方
```

#### 5.1 指标分类

```
┌─────────────────────────────────────────────────────────────┐
│                      BaseMetric                              │
│                      calculate(data)                         │
│                                                              │
│  ┌─────────────────┐    ┌─────────────────┐                  │
│  │  收益类指标       │    │  风险类指标       │                  │
│  │                  │    │                  │                  │
│  │  AnnualReturn    │    │  SharpeRatio     │                  │
│  │  calculate(      │    │  calculate(      │                  │
│  │    equity_curve) │    │    returns)      │                  │
│  │       → 年化收益  │    │       → 夏普比率  │                  │
│  │                  │    │                  │                  │
│  │                  │    │  SortinoRatio    │                  │
│  │                  │    │  calculate(      │                  │
│  │                  │    │    returns)      │                  │
│  │                  │    │       → 索提诺    │                  │
│  │                  │    │                  │                  │
│  │                  │    │  CalmarRatio     │                  │
│  │                  │    │  calculate(      │                  │
│  │                  │    │    equity_curve) │                  │
│  │                  │    │       → 卡玛比率  │                  │
│  │                  │    │                  │                  │
│  │                  │    │  MaxDrawdown     │                  │
│  │                  │    │  calculate(      │                  │
│  │                  │    │    equity_curve) │                  │
│  │                  │    │       → 最大回撤  │                  │
│  │                  │    │                  │                  │
│  │                  │    │  Volatility      │                  │
│  │                  │    │  calculate(      │                  │
│  │                  │    │    returns)      │                  │
│  │                  │    │       → 波动率    │                  │
│  └─────────────────┘    └─────────────────┘                  │
│                                                              │
│  ┌─────────────────┐    ┌─────────────────┐                  │
│  │  因子类指标       │    │  交易类指标       │                  │
│  │                  │    │                  │                  │
│  │  IC              │    │  WinRate         │                  │
│  │  calculate(      │    │  calculate(      │                  │
│  │    factor_vals,  │    │    returns)      │                  │
│  │    fwd_returns)  │    │       → 胜率     │                  │
│  │       → IC值     │    │                  │                  │
│  │                  │    │  Turnover        │                  │
│  │  RankIC          │    │  calculate(      │                  │
│  │  calculate(      │    │    positions)    │                  │
│  │    factor_vals,  │    │       → 换手率   │                  │
│  │    fwd_returns)  │    │                  │                  │
│  │       → RankIC   │    │                  │                  │
│  └─────────────────┘    └─────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

---

### 6. 完整数据流

```
数据源 (CSV / ClickHouse / AkShare / Wind / Parquet)
     │
     │  IDataProvider.get_bars()
     ▼
┌─────────────────────────────────────┐
│        原始行情数据 (DataFrame)        │
│  index: datetime                     │
│  columns: open/high/low/close/vol    │
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│      FactorEngine.compute()          │
│                                      │
│  factor_values = factor.compute(data)│
│                                      │
│  后端: Python / Numba / C++ / GPU    │
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│       因子值序列 (pd.Series)          │
│  index: datetime                     │
│  values: 因子值                      │
└─────────────────────────────────────┘
     │
     ├──→ BacktestEngine.run() ─────────────────────────────┐
     │       │                                               │
     │       ├── Portfolio 初始化                             │
     │       ├── 逐 bar: Order → Match → Fill → Update       │
     │       └── BacktestResult (equity_curve / fills)       │
     │                                                     │
     ├──→ MetricEngine.calculate() ─────────────────────────│
     │       │                                               │
     │       ├── AnnualReturn  (equity_curve)                │
     │       ├── SharpeRatio  (returns)                      │
     │       ├── SortinoRatio (returns)                      │
     │       ├── CalmarRatio  (equity_curve)                 │
     │       ├── MaxDrawdown  (equity_curve)                 │
     │       ├── Volatility   (returns)                      │
     │       ├── IC           (factor_vals, fwd_returns)     │
     │       ├── RankIC       (factor_vals, fwd_returns)     │
     │       ├── WinRate      (returns)                      │
     │       └── Turnover     (positions)                    │
     │                                                     │
     ▼                                                     ▼
┌─────────────────────┐            ┌─────────────────────────┐
│   BacktestResult    │            │   metrics: dict         │
│   equity_curve      │            │   sharpe: 1.23          │
│   orders / fills    │            │   calmar: 1.85          │
└─────────────────────┘            └─────────────────────────┘
     │                                                     │
     └─────────────────────┬───────────────────────────────┘
                           │
                           ▼
                    返回给 ResearchEngine
```

---

### 7. 四大引擎调用时序

```
ResearchEngine        DataEngine          FactorEngine        BacktestEngine        MetricEngine
    │                     │                    │                    │                    │
    │  get_bars()         │                    │                    │                    │
    │────────────────────>│                    │                    │                    │
    │                     │  IDataProvider     │                    │                    │
    │                     │  读取数据           │                    │                    │
    │<────────────────────│                    │                    │                    │
    │      data           │                    │                    │                    │
    │                     │                    │                    │                    │
    │  compute()          │                    │                    │                    │
    │─────────────────────────────────────────>│                    │                    │
    │                     │                    │  因子计算           │                    │
    │                     │                    │  Python/Numba/GPU  │                    │
    │<─────────────────────────────────────────│                    │                    │
    │     factor_values   │                    │                    │                    │
    │                     │                    │                    │                    │
    │  ── 可选: 回测 ──   │                    │                    │                    │
    │  run(strategy)      │                    │                    │                    │
    │──────────────────────────────────────────────────────────────>│                    │
    │                     │                    │                    │  Order → Match      │
    │                     │                    │                    │  Fill → Portfolio   │
    │<──────────────────────────────────────────────────────────────│                    │
    │     BacktestResult  │                    │                    │                    │
    │                     │                    │                    │                    │
    │  ── 计算指标 ──     │                    │                    │                    │
    │  calculate(metrics) │                    │                    │                    │
    │───────────────────────────────────────────────────────────────────────────────────>│
    │                     │                    │                    │  AnnualReturn      │
    │                     │                    │                    │  Sharpe/Sortino    │
    │                     │                    │                    │  Calmar/Drawdown   │
    │                     │                    │                    │  IC/RankIC         │
    │                     │                    │                    │  WinRate/Turnover  │
    │<───────────────────────────────────────────────────────────────────────────────────│
    │     metrics: dict   │                    │                    │                    │
```

---

### 8. 核心设计约束

| 约束 | 含义 |
|------|------|
| **DataEngine** | 对 Research 暴露 `IDataProvider` 接口，数据源对 Research 透明 |
| **FactorEngine** | Research 只写因子逻辑（`factor.compute`），不修改引擎代码 |
| **BacktestEngine** | 不计算 Sharpe 等指标，只做交易模拟 |
| **FactorEngine** | 不计算 IC 等指标，只做因子计算 |
| **MetricEngine** | 统一入口，Research 只调用 `metric.calculate(...)` |
