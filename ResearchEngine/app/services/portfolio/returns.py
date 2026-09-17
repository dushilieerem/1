"""因子组合的向量化收益计算。

本模块只处理已经构造好的持仓/分组产物，不负责数据读取或因子计算。
核心路径只做一次个股收益矩阵 ``close.pct_change()``，主组合和分组
收益都从这份矩阵聚合，避免按分组重复扫描完整行情。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class GrossReturnBundle:
    """一次向量化计算得到的组合收益中间结果。"""

    asset_returns: pd.DataFrame
    held_weights: pd.DataFrame
    portfolio_returns: pd.Series
    weight_change: pd.DataFrame
    turnover: pd.Series


def calculate_gross_returns(
    close: pd.DataFrame,
    positions: pd.DataFrame,
) -> GrossReturnBundle:
    """计算不含交易成本的组合收益及换手明细。"""

    prices = close.reindex(index=positions.index, columns=positions.columns)
    asset_returns = prices.pct_change(fill_method=None)
    held = positions.ffill().fillna(0.0)
    portfolio_returns = held.mul(asset_returns).sum(axis=1)
    weight_change = held.diff().fillna(0.0)
    turnover = weight_change.abs().sum(axis=1)
    return GrossReturnBundle(
        asset_returns=asset_returns,
        held_weights=held,
        portfolio_returns=portfolio_returns,
        weight_change=weight_change,
        turnover=turnover,
    )


def calculate_group_returns(
    asset_returns: pd.DataFrame,
    group_assignments: pd.DataFrame,
    rebalance_mask: pd.Series,
    n_groups: int,
) -> pd.DataFrame:
    """一次性计算所有分组的等权毛收益。

    ``group_assignments[t]`` 是 t 日收盘形成的分组；收益在下一交易日
    承担，因此先用 NumPy 的索引传播得到每个交易日的上一调仓分组，
    再用 ``bincount`` 按 ``(date, group)`` 聚合收益和成员数。整个过程
    不创建每个分组的 ``T×N`` 权重表，也不包含 Python 日期/标的循环。
    """

    if n_groups < 2:
        raise ValueError(f"n_groups 至少为 2，得到 {n_groups}")
    if asset_returns.empty or group_assignments.empty:
        return pd.DataFrame(
            index=asset_returns.index,
            columns=[f"Q{number}" for number in range(1, n_groups + 1)],
            dtype=float,
        ).iloc[1:]

    assignments = group_assignments.reindex(
        index=asset_returns.index,
        columns=asset_returns.columns,
    )
    assignment_values = assignments.to_numpy(dtype=float, na_value=np.nan)
    returns = asset_returns.to_numpy(dtype=float, na_value=np.nan)
    n_dates, n_symbols = assignment_values.shape

    rebalance_values = rebalance_mask.reindex(asset_returns.index).to_numpy(
        dtype=bool
    )
    signal_rows = np.where(rebalance_values, np.arange(n_dates), -1)
    previous_signal = np.full(n_dates, -1, dtype=np.intp)
    if n_dates > 1:
        previous_signal[1:] = np.maximum.accumulate(signal_rows[:-1])

    # 将每个收益日映射到上一调仓日的组号；-1 表示尚未入场或当日无效。
    held_groups = np.full_like(assignment_values, np.nan, dtype=float)
    has_previous_signal = previous_signal >= 0
    held_groups[has_previous_signal] = (
        assignment_values[previous_signal[has_previous_signal]] - 1.0
    )
    member = (
        np.isfinite(held_groups)
        & (held_groups >= 0)
        & (held_groups < n_groups)
    )
    group_codes = np.where(member, held_groups, 0).astype(np.intp, copy=False)
    date_codes = np.broadcast_to(
        np.arange(n_dates, dtype=np.intp)[:, None],
        (n_dates, n_symbols),
    )

    count_keys = date_codes[member] * n_groups + group_codes[member]
    counts = np.bincount(
        count_keys,
        minlength=n_dates * n_groups,
    ).reshape(n_dates, n_groups)

    valid_returns = member & ~np.isnan(returns)
    return_keys = date_codes[valid_returns] * n_groups + group_codes[valid_returns]
    sums = np.bincount(
        return_keys,
        weights=returns[valid_returns],
        minlength=n_dates * n_groups,
    ).reshape(n_dates, n_groups)
    group_values = np.divide(
        sums,
        counts,
        out=np.zeros_like(sums, dtype=float),
        where=counts > 0,
    )
    result = pd.DataFrame(
        group_values,
        index=asset_returns.index,
        columns=[f"Q{number}" for number in range(1, n_groups + 1)],
    )
    # 与原组合收益口径一致：首日是信号日，没有持有收益。
    return result.iloc[1:]


__all__ = [
    "GrossReturnBundle",
    "calculate_gross_returns",
    "calculate_group_returns",
]
