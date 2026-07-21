"""QuantCore - 底层量化引擎。

依据 `docs/04-features/FEAT-001-quantcore-core/03-modules.md` 划分为四大引擎，各自职责清晰、互不越界：

- ``data``      : DataEngine    - 统一数据读取，对 Research 暴露 ``IDataProvider``
- ``factor``    : FactorEngine  - 因子计算，Research 只写因子逻辑
- ``backtest``  : BacktestEngine - 交易模拟，不计算任何指标
- ``metric``    : MetricEngine  - 所有指标的统一入口（非常重要）
"""

from quantcore.data.engine import DataEngine
from quantcore.data.interface import IDataProvider
from quantcore.data.providers import (
    AkShareProvider,
    ClickHouseProvider,
    CSVDataProvider,
    FieldParquetProvider,
    ParquetProvider,
    WideCSVProvider,
    WindProvider,
)
from quantcore.factor.backend import ComputeBackend, PythonBackend, get_backend
from quantcore.factor.base import BaseFactor, FactorLibrary, Panel
from quantcore.factor.engine import FactorEngine
from quantcore.backtest.engine import BacktestEngine
from quantcore.backtest.cost import TransactionCost
from quantcore.backtest.matching import MatchingEngine
from quantcore.backtest.order import Fill, Order
from quantcore.backtest.portfolio import Portfolio, Position
from quantcore.backtest.result import BacktestResult
from quantcore.backtest.adapter import (
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
from quantcore.metric.base import BaseMetric
from quantcore.metric.context import MetricContext
from quantcore.metric.engine import MetricEngine

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
    "BacktestEngine",
    "MatchingEngine",
    "TransactionCost",
    "Order",
    "Fill",
    "Position",
    "Portfolio",
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
