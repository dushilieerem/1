"""BacktestEngine 子包。

含两套回测：

- **事件驱动** ``BacktestEngine``（bar-loop + MatchingEngine + Order/Fill）：仅 demo 用，
  保留为未来 EventEngine 基座。
- **向量化适配层** :mod:`quantcore.backtest.adapter`：可插拔后端（Native / VectorBT），
  ResearchEngine 实际走这条。详见 ``docs/04-features/FEAT-003-backtest-adapter/03-technical-design.md``。
"""

from quantcore.backtest.adapter import (  # noqa: F401
    BacktestConfig,
    BacktestSignals,
    FactorGroupStrategy,
    FactorQuantileStrategy,
    IBacktestEngine,
    ICalendar,
    IDataFeed,
    IExecution,
    IMetrics,
    IPortfolio,
    IStrategy,
    NativeEngine,
    PandasCalendar,
    get_backtest_engine,
)
