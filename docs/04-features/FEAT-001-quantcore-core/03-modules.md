## QuantCore

```
QuantCore
├── data/      DataEngine + IDataProvider（csv/parquet/field_parquet/wide_csv/clickhouse/akshare/wind）
├── factor/    FactorEngine + BaseFactor / Panel（FactorLibrary 风格）
├── metric/    MetricEngine + MetricContext（10 个标准指标）
└── backtest/
    ├── engine/    事件驱动 BacktestEngine（bar-loop + MatchingEngine + Order/Fill，保留为未来 EventEngine 基座）
    └── adapter/   向量化适配层（IBacktestEngine: Native | VectorBT，ResearchEngine 实际走这条）
```

## Data Engine

负责：

统一读取数据。

例如：

以后：

```
CSV

ClickHouse

AkShare

Wind

Parquet
```

Research：

永远不知道。

数据来自哪里。

只知道：

```
IDataProvider
```

## Factor Engine

负责：

真正计算：

```
factor.compute(...)
```

支持：

```
Python

C++

Numba

GPU
```

以后：

Research：

完全不用改。

## Backtest Engine

负责：

整个：

交易模拟。

例如：

```
撮合

手续费

滑点

成交

现金变化
```

Research：

不要知道。

## Backtest Adapter（向量化适配层）⭐

`backtest/adapter/`：可插拔回测后端，ResearchEngine 经 ``IBacktestEngine`` 契约按 config 切换。

```
IStrategy.generate_signals(panel) -> BacktestSignals(target_weights)
                                              │
                              IBacktestEngine.run(signals, config)
                              ├── NativeEngine    自研向量化（默认，与 build_factor_portfolio 逐位等价）
                              └── VectorBTEngine   vectorbt 后端（懒加载）
                                              │
                                              ▼
                              BacktestResult(equity_curve / returns / positions)
```

领域接口：``IStrategy`` / ``IDataFeed`` / ``IPortfolio`` / ``IExecution`` / ``ICalendar`` / ``IMetrics``。
向量化后端只遵守顶层 ``IBacktestEngine.run`` 契约，内化 portfolio/execution；事件驱动自研引擎
（未来 EventEngine）才把后三者当可插拔件。详见 ``../FEAT-003-backtest-adapter/03-technical-design.md``。

## Metric Engine（非常重要）

负责：

所有指标。

例如：

```
Annual Return

Sharpe

Sortino

Calmar

Drawdown

IC

RankIC

WinRate

Turnover

Volatility
```

注意：

不要：

Backtest：

算Sharpe。

不要：

Factor：

算IC。

统一：

Metric。

以后：

Research：

只调用：

```
metric.calculate(...)
```

