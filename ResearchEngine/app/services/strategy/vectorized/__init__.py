"""回测适配层：Native 向量化回测后端。

把「策略产出目标权重 -> 后端模拟 -> 净值/收益/持仓」做成后端无关的契约：
app 只调 :func:`get_backtest_engine` + :class:`IBacktestEngine.run`，
因子代码与公共 API 通过统一契约调用 NativeEngine。

详见 ``docs/03-功能文档/FEAT-003-回测适配层/03-technical-design.md``。
"""

from app.services.data.calendar import PandasCalendar
from app.services.strategy.vectorized.interfaces import (
    IBacktestEngine,
    IDataFeed,
    IExecution,
    IMetrics,
    IPortfolio,
    IStrategy,
)
from app.services.data.calendar import ICalendar
from app.services.strategy.vectorized.native_engine import NativeEngine
from app.services.strategy.vectorized.registry import get_backtest_engine
from app.models.strategy import BacktestConfig, BacktestSignals
from app.services.strategy.vectorized.strategies import FactorGroupStrategy, FactorQuantileStrategy
from app.services.strategy.vectorized.factor_strategy import (
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
