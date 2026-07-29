"""回测适配层：可插拔后端（Native / VectorBT）。

把「策略产出目标权重 -> 后端模拟 -> 净值/收益/持仓」做成后端无关的契约：
ResearchEngine 只调 :func:`get_backtest_engine` + :class:`IBacktestEngine.run`，
切后端 = 换 config，因子代码与公共 API 零改动。

详见 ``docs/04-features/FEAT-003-backtest-adapter/03-technical-design.md``。
"""

from quantcore.backtest.adapter.calendar import PandasCalendar
from quantcore.backtest.adapter.interfaces import (
    IBacktestEngine,
    ICalendar,
    IDataFeed,
    IExecution,
    IMetrics,
    IPortfolio,
    IStrategy,
)
from quantcore.backtest.adapter.native_engine import NativeEngine
from quantcore.backtest.adapter.registry import get_backtest_engine
from quantcore.backtest.adapter.signals import BacktestConfig, BacktestSignals
from quantcore.backtest.adapter.strategies import FactorGroupStrategy, FactorQuantileStrategy
from quantcore.backtest.adapter.factor_strategy import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    Universe,
    factor,
    signal,
)

__all__ = [
    # 信号 / 配置
    "BacktestSignals",
    "BacktestConfig",
    # 接口
    "IStrategy",
    "IDataFeed",
    "IPortfolio",
    "IExecution",
    "ICalendar",
    "IMetrics",
    "IBacktestEngine",
    # 默认实现
    "PandasCalendar",
    "FactorGroupStrategy",
    "FactorQuantileStrategy",
    "FactorPortfolioStrategy",
    "Universe",
    "TopN",
    "EqualWeight",
    "EveryNTradingDays",
    "factor",
    "signal",
    "NativeEngine",
    "get_backtest_engine",
]
