"""因子组合构建（研究编排辅助）。

历史职责：把因子值转化为可衡量的组合净值，用于收益/风险/胜率/换手等指标。

自适配层改造后，本模块仅保留**薄包装**用于向后兼容
（``researchengine.__init__`` 导出与既有调用方）。真实逻辑已迁移至
:mod:`quantcore.backtest.adapter`：

- 因子值 -> 目标权重：:class:`quantcore.backtest.adapter.FactorQuantileStrategy`
- 目标权重 -> 净值/收益/持仓：:class:`quantcore.backtest.adapter.NativeEngine`

新代码应直接用 ``IBacktestEngine`` + ``IStrategy``，按 ``backtest.engine`` 切后端。
"""

from __future__ import annotations

from typing import Tuple

import numpy as np  # noqa: F401  (forward_returns 等保留 numpy 依赖，便于外部扩展)
import pandas as pd

from quantcore.data._util import resolve_universe


def build_close_panel(data_engine, universe, start=None, end=None) -> pd.DataFrame:
    """从 data_engine 读取 universe 的收盘价宽表 ``日期×标的``（走面板接口）。"""
    panels = data_engine.get_panels(start, end, ["close"])
    close = panels.get("close")
    if close is None or close.empty:
        return pd.DataFrame()
    symbols = resolve_universe(data_engine, universe)
    return close.reindex(columns=symbols)


def forward_returns(close_panel: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """计算远期收益 ``日期×标的``：``forward_ret[t] = close[t+h]/close[t] - 1``。

    与因子值按日期对齐：因子在 t 的值对应 t->t+h 的远期收益。
    """
    return (close_panel.shift(-horizon) / close_panel - 1.0)


def _rebalance_mask(index: pd.DatetimeIndex, freq: str) -> pd.Series:
    """生成布尔序列，标记每个日期是否为调仓日（首行必为调仓日）。

    已迁移至 :class:`quantcore.backtest.adapter.calendar.PandasCalendar`；此处保留薄包装
    以兼容既有导入。"""
    from quantcore.backtest.adapter.calendar import PandasCalendar

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

    薄包装：委托 :class:`NativeEngine` + :class:`FactorQuantileStrategy`，与历史实现**逐位等价**
    （默认 ``cost=0``，固定本金口径 ``equity = 1.0 + port_ret.cumsum()``）。

    Returns
    -------
    equity_curve : pd.Series
    returns : pd.Series
    positions : pd.DataFrame
        实际持有的权重 ``日期×标的``，用于换手率。
    """
    from quantcore.backtest.adapter import (
        BacktestConfig,
        FactorQuantileStrategy,
        NativeEngine,
    )

    strategy = FactorQuantileStrategy(
        factor_values,
        close_panel,
        rebalance=rebalance,
        stock_num=stock_num,
        long_short=long_short,
    )
    signals = strategy.generate_signals()
    result = NativeEngine().run(signals, BacktestConfig())
    return result.equity_curve, result.returns, result.positions
