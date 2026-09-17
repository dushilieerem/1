"""因子组合构建（研究编排辅助）。

历史职责：把因子值转化为可衡量的组合净值，用于收益/风险/胜率/换手等指标。

重构后，本模块仅保留**兼容门面**（``app.__init__`` 导出与既有调用方）。真实逻辑由
QuantCore 的 ``PortfolioEngine`` 和 ``MetricEngine`` 提供；策略侧的
``FactorQuantileStrategy`` / ``NativeEngine`` 不再参与因子组合构建。
"""

from __future__ import annotations

from typing import Tuple

import pandas as pd

from app.services.metric.engine import MetricEngine
from app.services.portfolio.engine import PortfolioEngine
from app.utils.data import first_panel_date
from app.services.data.universe import resolve_universe


def build_close_panel(data_engine, universe, start=None, end=None) -> pd.DataFrame:
    """从 data_engine 读取 universe 的收盘价宽表 ``日期×标的``（走面板接口）。"""
    panels = data_engine.get_panels(start, end, ["close"])
    close = panels.get("close")
    if close is None or close.empty:
        return pd.DataFrame()
    symbols = resolve_universe(
        data_engine, universe, as_of=first_panel_date(panels)
    )
    return close.reindex(columns=symbols)


def forward_returns(close_panel: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """计算远期收益 ``日期×标的``：``forward_ret[t] = close[t+h]/close[t] - 1``。

    与因子值按日期对齐：因子在 t 的值对应 t->t+h 的远期收益。
    """
    return (close_panel.shift(-horizon) / close_panel - 1.0)


def _rebalance_mask(index: pd.DatetimeIndex, freq: str) -> pd.Series:
    """生成布尔序列，标记每个日期是否为调仓日（首行必为调仓日）。

    已迁移至 :class:`app.services.data.calendar.PandasCalendar`；此处保留薄包装
    以兼容既有导入。"""
    from app.services.data.calendar import PandasCalendar

    return PandasCalendar().rebalance_mask(index, freq)


def build_factor_portfolio(
    factor_values: pd.DataFrame,
    close_panel: pd.DataFrame,
    rebalance: str = "monthly",
    stock_num: int = 100,
    long_short: bool = True,
) -> Tuple[pd.Series, pd.Series, pd.DataFrame]:
    """由因子值构建组合，返回 (净值曲线, 收益率序列, 持仓权重)。

    策略：每个调仓日按因子值截面排名，做多因子值最大的 ``stock_num`` 只（等权）；
    若 ``long_short`` 另做空因子值最小的 ``stock_num`` 只。持仓至下一调仓日。

    薄包装：委托 ``PortfolioEngine`` + ``MetricEngine``，保持旧的返回三元组和
    收益/展示净值时序。

    Returns
    -------
    equity_curve : pd.Series
    returns : pd.Series
    positions : pd.DataFrame
        实际持有的权重 ``日期×标的``，用于换手率。
    """
    portfolio = PortfolioEngine().build(
        factor_values,
        close_panel,
        groups=None,
        rebalance=rebalance,
        stock_num=stock_num,
        portfolio_type="long_short" if long_short else "long_only",
    )
    evaluation = MetricEngine().evaluate(portfolio)
    return (
        evaluation["equity_curve"],
        evaluation["returns"],
        evaluation["positions"],
    )
