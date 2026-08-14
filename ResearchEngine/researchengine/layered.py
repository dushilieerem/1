"""分层回测引擎 - 因子评估的公共底座。

按任意截面值（因子值 / 市值 / 账面市值比）把标的分 N 组，各组等权持有至下一调仓日，
计算各组累计净值与多空收益。``t`` 收盘分组对应 ``t -> t+1`` 收益；首个输出日
保留首个持有日收益，后续按复利累计。
供分层回测图、分市值分层、SMB/HML 因子构造复用。

入口：
- :func:`layered_equity` - 各组累计净值（画分层回测图）
- :func:`long_short_returns` - 多空日收益（做多最高组、做空最低组，画多空收益图 / 喂回归）
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from quantcore.backtest.adapter.calendar import PandasCalendar
from quantcore.backtest.adapter.grouping import raw_qcut_groups


def quantile_groups(
    group_values: pd.DataFrame,
    n_groups: int = 5,
) -> pd.DataFrame:
    """截面分位分组。

    每行（每个日期）按 ``group_values`` 把有效标的等分为 ``n_groups`` 组，
    返回**同形状的组号 DataFrame**（1..N，NaN 表示当日无效）。
    Q1 = 因子值最高组 ... QN = 最低组。

    使用 ``pd.qcut`` 按原始值确定边界；退化重复值截面由公共分组函数
    做稳定兜底，有效标的不足时保持 qcut 的实际分箱结果。

    Parameters
    ----------
    group_values : pd.DataFrame
        ``日期×标的`` 截面值（因子值 / 市值 / 账面市值比 ...）。
    n_groups : int
        分组数（默认 5）。

    Returns
    -------
    pd.DataFrame
        组号 1..N，与 ``group_values`` 同形状；原 NaN 处仍为 NaN。
    """
    if n_groups < 2:
        raise ValueError(f"n_groups 至少为 2，得到 {n_groups}")
    return raw_qcut_groups(group_values, n_groups)


def layered_returns(
    group_values: pd.DataFrame,
    close: pd.DataFrame,
    n_groups: int = 5,
    rebalance: str = "monthly",
    calendar: Optional[PandasCalendar] = None,
    group_assignments: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """各组日收益（等权）：``t`` 收盘定组，``t+1`` 收盘承担当日收益。

    前一交易日的分组承担当日收盘到收盘收益；首个信号日没有持仓并剔除，
    首个保留日包含首个持有日收益，组内等权、后续复利。

    Parameters
    ----------
    group_values : pd.DataFrame
        ``日期×标的`` 分组依据（因子值 / 市值 ...）。
    close : pd.DataFrame
        ``日期×标的`` 收盘价，用于算个股日收益。
    n_groups : int
        分组数（默认 5）。
    rebalance : str
        调仓频率 daily/weekly/monthly（默认 monthly）。
    calendar : PandasCalendar, optional
        调仓日历，默认新建。
    group_assignments : pd.DataFrame, optional
        已按 ``group_values`` 原始值计算好的组号。提供时复用该结果，
        避免在同一次回测中重复执行 ``pd.qcut``。

    Returns
    -------
    pd.DataFrame
        ``日期×N组``，列名 ``Q1..QN``（Q1 最高组）。首日（无持仓）已剔除。
    """
    common_dates = group_values.index.intersection(close.index)
    common_symbols = group_values.columns.intersection(close.columns)
    if common_dates.empty or common_symbols.empty:
        return pd.DataFrame()
    gv = group_values.loc[common_dates, common_symbols]
    close = close.loc[common_dates, common_symbols]

    ret = close.pct_change()
    groups = (
        quantile_groups(gv, n_groups)
        if group_assignments is None
        else group_assignments.reindex(index=gv.index, columns=gv.columns)
    )
    reb_mask = (calendar or PandasCalendar()).rebalance_mask(gv.index, rebalance)
    reb_np = reb_mask.to_numpy()[:, None]

    out: dict[str, pd.Series] = {}
    for g in range(1, n_groups + 1):
        mask = (groups == g).fillna(False).astype(float).to_numpy()  # (T, N) 0/1
        n_in = mask.sum(axis=1, keepdims=True)         # (T,1) 组内成员数
        safe_n = np.where(n_in > 0, n_in, 1.0)
        weight = mask / safe_n                          # 等权
        # 仅调仓日更新权重；前一日分组承担当日收盘收益。
        weight = np.where(reb_np, weight, np.nan)
        weight = pd.DataFrame(weight, index=gv.index, columns=gv.columns)
        held = weight.ffill().shift(1).fillna(0.0)
        group_ret = (held * ret).sum(axis=1)
        out[f"Q{g}"] = group_ret

    result = pd.DataFrame(out)
    result = result.iloc[1:]  # 去信号日；首个保留日包含首个持有日收益。
    return result.dropna(how="all")


def layered_equity(layered_returns_df: pd.DataFrame) -> pd.DataFrame:
    """各组累计净值，首个输出日统一归一为 1.0。

    ``layered_returns_df`` 仍保留首个信号到入场日的原始收益，供指标
    计算使用；展示曲线从入场日归一，后续收益按复利累计。

    Parameters
    ----------
    layered_returns_df : pd.DataFrame
        :func:`layered_returns` 的输出，列名 ``Q1..QN``。

    Returns
    -------
    pd.DataFrame
        各组累计净值，首值为 1.0。
    """
    if layered_returns_df is None or layered_returns_df.empty:
        return layered_returns_df.copy() if layered_returns_df is not None else pd.DataFrame()
    display_returns = layered_returns_df.copy()
    display_returns.iloc[0] = 0.0
    return (1.0 + display_returns).cumprod()


def long_short_returns(
    layered_returns_df: pd.DataFrame,
    q_low: Optional[int] = None,
    q_high: Optional[int] = None,
) -> pd.Series:
    """多空日收益 = 最高组 - 最低组（默认 ``Q1 − QN``）。

    Parameters
    ----------
    layered_returns_df : pd.DataFrame
        :func:`layered_returns` 的输出。
    q_low : int
        做空的组号（默认最大组号，因子值最低组）。
    q_high : int, optional
        做多的组号（默认 1，因子值最高组）。

    Returns
    -------
    pd.Series
        多空日收益。
    """
    qcols = [c for c in layered_returns_df.columns if c.startswith("Q")]
    if not qcols:
        raise ValueError("layered_returns_df 无 Q* 列")
    max_group = max(int(c[1:]) for c in qcols)
    if q_high is None:
        q_high = 1
    if q_low is None:
        q_low = max_group
    col_high, col_low = f"Q{q_high}", f"Q{q_low}"
    if col_high not in layered_returns_df.columns or col_low not in layered_returns_df.columns:
        raise KeyError(f"缺少组列: {col_high} 或 {col_low}")
    return layered_returns_df[col_high] - layered_returns_df[col_low]
