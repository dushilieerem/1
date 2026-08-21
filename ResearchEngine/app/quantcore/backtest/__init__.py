"""BacktestEngine 子包。

含两套回测：

- **事件驱动** :mod:`app.quantcore.backtest.event`：A 股日频 EventEngine。
- **向量化适配层** :mod:`app.quantcore.backtest.adapter`：NativeEngine，供 app 使用。
"""

from app.quantcore.backtest.event import EventBacktestConfig, EventBacktestEngine

from app.quantcore.backtest.adapter import (  # noqa: F401
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

__all__ = ["EventBacktestConfig", "EventBacktestEngine"]
