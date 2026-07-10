"""因子组合构建（研究编排辅助）。

把因子值转化为可衡量的组合净值，用于收益/风险/胜率/换手等指标。
这是 ResearchEngine 的「组织流程」部分：调用 QuantCore 取数据与因子值，
再自行决定如何把因子变成收益（向量化分位组合），**不**侵入 QuantCore 引擎。
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
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
    """生成布尔序列，标记每个日期是否为调仓日。

    取每个调仓周期的首个交易日（首行必为调仓日）。
    """
    if freq in ("daily", "d", "1d"):
        return pd.Series(True, index=index)
    if freq in ("weekly", "w"):
        iso = index.isocalendar()
        year_week = pd.Series(list(zip(iso.year, iso.week)), index=index)
        return ~year_week.duplicated()
    if freq in ("monthly", "m"):
        ym = pd.Series(index.year * 100 + index.month, index=index)
        return ~ym.duplicated()
    # 默认每月
    ym = pd.Series(index.year * 100 + index.month, index=index)
    return ~ym.duplicated()


def build_factor_portfolio(
    factor_values: pd.DataFrame,
    close_panel: pd.DataFrame,
    rebalance: str = "monthly",
    n_groups: int = 5,
    long_short: bool = True,
) -> Tuple[pd.Series, pd.Series, pd.DataFrame]:
    """由因子值构建分位组合，返回 (净值曲线, 收益率序列, 持仓权重)。

    策略：每个调仓日按因子值截面排名，做多最高分位、做空最低分位（若 long_short），
    组内等权；持仓至下一调仓日。

    Returns
    -------
    equity_curve : pd.Series
    returns : pd.Series
    positions : pd.DataFrame
        实际持有的权重 ``日期×标的``，用于换手率。
    """
    # 对齐
    common_dates = factor_values.index.intersection(close_panel.index)
    common_symbols = factor_values.columns.intersection(close_panel.columns)
    fv = factor_values.loc[common_dates, common_symbols]
    close = close_panel.loc[common_dates, common_symbols]
    ret = close.pct_change()

    reb_mask = _rebalance_mask(fv.index, rebalance)

    # 目标权重：仅在调仓日赋值，其余为 NaN（便于 ffill 持有至下一调仓日）
    target = pd.DataFrame(np.nan, index=fv.index, columns=fv.columns)
    for date in fv.index:
        if not reb_mask.loc[date]:
            continue
        row = fv.loc[date].dropna()
        if len(row) < n_groups:
            continue
        # 降序排名：1 = 因子值最大
        ranks = row.rank(ascending=False, method="first")
        n_top = max(1, len(row) // n_groups)
        w = pd.Series(0.0, index=row.index)
        top = ranks[ranks <= n_top].index
        w.loc[top] = 1.0 / len(top)
        if long_short:
            bottom = ranks[ranks > (len(row) - n_top)].index
            w.loc[bottom] = -1.0 / len(bottom)
        target.loc[date, w.index] = w.values

    # 实际持有权重 = 上一日收盘的目标权重（t 收盘调仓，t+1 起持有），区间内 ffill
    held = target.ffill().shift(1).fillna(0.0)
    port_ret = (held * ret).sum(axis=1)
    # 去掉首日（无持仓）
    port_ret = port_ret.iloc[1:]
    port_ret = port_ret.dropna()

    equity = (1.0 + port_ret).cumprod()
    positions = held.loc[port_ret.index].copy()
    return equity, port_ret, positions
