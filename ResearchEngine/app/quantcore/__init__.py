"""QuantCore - 底层量化引擎。

依据 `docs/04-features/FEAT-001-app.quantcore-core/03-modules.md` 划分为四大引擎，各自职责清晰、互不越界：

- ``data``      : DataEngine    - 统一数据读取，对 Research 暴露 ``IDataProvider``
- ``factor``    : FactorEngine  - 因子计算，Research 只写因子逻辑
- ``backtest``  : EventBacktestEngine 与向量化回测
- ``metric``    : MetricEngine  - 所有指标的统一入口（非常重要）
"""

from app.quantcore.data.engine import DataEngine
from app.quantcore.data.interface import IDataProvider
from app.quantcore.data.providers import (
    AkShareProvider,
    ClickHouseProvider,
    CSVDataProvider,
    FieldParquetProvider,
    ParquetProvider,
    WideCSVProvider,
    WindProvider,
)
from app.quantcore.factor.backend import ComputeBackend, PythonBackend, get_backend
from app.quantcore.factor.base import BaseFactor, FactorLibrary, Panel
from app.quantcore.factor.engine import FactorEngine
from app.quantcore.backtest.result import BacktestResult
from app.quantcore.backtest.event import (
    EventBacktestConfig,
    EventBacktestEngine,
    EventBacktestResult,
    EventFill,
    EventOrder,
    EventStrategy,
    PositionSnapshot,
    StrategyContext,
)
from app.quantcore.backtest.adapter import (
    BacktestConfig,
    BacktestSignals,
    FactorGroupStrategy,
    FactorQuantileStrategy,
    FactorPortfolioStrategy,
    Universe,
    TopN,
    EqualWeight,
    EveryNTradingDays,
    factor,
    signal,
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
from app.quantcore.metric.base import BaseMetric
from app.quantcore.metric.context import MetricContext
from app.quantcore.metric.engine import MetricEngine

__all__ = [
    # Data
    "DataEngine",
    "IDataProvider",
    "CSVDataProvider",
    "ParquetProvider",
    "FieldParquetProvider",
    "WideCSVProvider",
    "ClickHouseProvider",
    "AkShareProvider",
    "WindProvider",
    # Factor
    "FactorEngine",
    "BaseFactor",
    "FactorLibrary",
    "Panel",
    "ComputeBackend",
    "PythonBackend",
    # Backtest
    "EventBacktestConfig",
    "EventBacktestEngine",
    "EventBacktestResult",
    "EventFill",
    "EventOrder",
    "EventStrategy",
    "PositionSnapshot",
    "StrategyContext",
    "BacktestResult",
    # Backtest Adapter（可插拔后端）
    "IBacktestEngine",
    "IStrategy",
    "IDataFeed",
    "IPortfolio",
    "IExecution",
    "ICalendar",
    "IMetrics",
    "BacktestSignals",
    "BacktestConfig",
    "FactorQuantileStrategy",
    "FactorGroupStrategy",
    "FactorPortfolioStrategy",
    "Universe",
    "TopN",
    "EqualWeight",
    "EveryNTradingDays",
    "factor",
    "signal",
    "NativeEngine",
    "PandasCalendar",
    "get_backtest_engine",
    # Metric
    "MetricEngine",
    "BaseMetric",
    "MetricContext",
]
