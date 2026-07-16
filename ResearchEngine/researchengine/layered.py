"""分层回测引擎 - 因子评估的公共底座。

按任意截面值（因子值 / 市值 / 账面市值比）把标的分 N 组，各组等权持有至下一调仓日，
计算各组累计净值与多空收益。净值数学与 :class:`quantcore.backtest.adapter.NativeEngine`
逐位一致（固定本金 ``equity = 1.0 + port_ret.cumsum()``、``t`` 收盘分组 -> ``t+1`` 起持有），
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


def quantile_groups(
    group_values: pd.DataFrame,
    n_groups: int = 5,
) -> pd.DataFrame:
    """截面分位分组。

    每行（每个日期）按 ``group_values`` 把有效标的等分为 ``n_groups`` 组，
    返回**同形状的组号 DataFrame**（1..N，NaN 表示当日无效）。
    Q1 = 因子值最低组 ... QN = 最高组。

    用 rank 分位（``pct=True``）而非 ``pd.qcut``，规避重复值 ``duplicates`` 报错；
    有效标的不足 ``n_groups`` 时，组号会跨多个 rank 落在同一组（自然降级，不报错）。

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
    # pct rank: 每个值在当日截面的分位 (0,1]，NaN 保持 NaN
    ranks = group_values.rank(axis=1, pct=True, method="average")
    groups = np.ceil(ranks * n_groups).clip(upper=n_groups)
    groups = groups.where(group_values.notna())
    return groups.astype("Int64")  # 可空整数


def layered_returns(
    group_values: pd.DataFrame,
    close: pd.DataFrame,
    n_groups: int = 5,
    rebalance: str = "monthly",
    calendar: Optional[PandasCalendar] = None,
) -> pd.DataFrame:
    """各组日收益（等权），调仓日更新分组，``t`` 收盘定权 -> ``t+1`` 起持有。

    口径与 :class:`NativeEngine` 一致：目标权重在调仓日确定、区间内 ffill、
    ``shift(1)`` 后乘以个股日收益；固定本金，组内等权。

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

    Returns
    -------
    pd.DataFrame
        ``日期×N组``，列名 ``Q1..QN``（Q1 最低组）。首日（无持仓）已剔除。
    """
    common_dates = group_values.index.intersection(close.index)
    common_symbols = group_values.columns.intersection(close.columns)
    if common_dates.empty or common_symbols.empty:
        return pd.DataFrame()
    gv = group_values.loc[common_dates, common_symbols]
    close = close.loc[common_dates, common_symbols]

    ret = close.pct_change()
    groups = quantile_groups(gv, n_groups)
    reb_mask = (calendar or PandasCalendar()).rebalance_mask(gv.index, rebalance)
    reb_np = reb_mask.to_numpy()[:, None]

    out: dict[str, pd.Series] = {}
    for g in range(1, n_groups + 1):
        mask = (groups == g).fillna(False).astype(float).to_numpy()  # (T, N) 0/1
        n_in = mask.sum(axis=1, keepdims=True)         # (T,1) 组内成员数
        safe_n = np.where(n_in > 0, n_in, 1.0)
        weight = mask / safe_n                          # 等权
        # 仅调仓日更新权重 -> ffill 到下一调仓日 -> shift(1) 持有时序
        weight = np.where(reb_np, weight, np.nan)
        weight = pd.DataFrame(weight, index=gv.index, columns=gv.columns)
        held = weight.ffill().shift(1).fillna(0.0)
        group_ret = (held * ret).sum(axis=1)
        out[f"Q{g}"] = group_ret

    result = pd.DataFrame(out)
    result = result.iloc[1:]  # 去首日（pct_change 首日 NaN、无持仓）
    return result.dropna(how="all")


def layered_equity(layered_returns_df: pd.DataFrame) -> pd.DataFrame:
    """各组累计净值 = ``1 + 日收益累加``（固定本金口径）。

    Parameters
    ----------
    layered_returns_df : pd.DataFrame
        :func:`layered_returns` 的输出，列名 ``Q1..QN``。

    Returns
    -------
    pd.DataFrame
        各组累计净值，首值 1.0。
    """
    return 1.0 + layered_returns_df.cumsum()


def long_short_returns(
    layered_returns_df: pd.DataFrame,
    q_low: int = 1,
    q_high: Optional[int] = None,
) -> pd.Series:
    """多空日收益 = 最高组 - 最低组（默认 ``QN − Q1``）。

    Parameters
    ----------
    layered_returns_df : pd.DataFrame
        :func:`layered_returns` 的输出。
    q_low : int
        做空的组号（默认 1，因子值最低组）。
    q_high : int, optional
        做多的组号，默认取最大组号（因子值最高组）。

    Returns
    -------
    pd.Series
        多空日收益。
    """
    qcols = [c for c in layered_returns_df.columns if c.startswith("Q")]
    if not qcols:
        raise ValueError("layered_returns_df 无 Q* 列")
    if q_high is None:
        q_high = max(int(c[1:]) for c in qcols)
    col_high, col_low = f"Q{q_high}", f"Q{q_low}"
    if col_high not in layered_returns_df.columns or col_low not in layered_returns_df.columns:
        raise KeyError(f"缺少组列: {col_high} 或 {col_low}")
    return layered_returns_df[col_high] - layered_returns_df[col_low]
