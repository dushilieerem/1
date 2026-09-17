"""内置策略：因子分位组合。

把 :func:`app.services.factor.portfolio.build_factor_portfolio` 里「因子值 -> 目标权重」的部分
提炼成一个 :class:`IStrategy`：每个调仓日按因子值截面排名，做多因子值最大的 ``stock_num`` 只
（等权）；若 ``long_short`` 另做空因子值最小的 ``stock_num`` 只。产出 ``BacktestSignals``，
交由 :class:`NativeEngine` 模拟。

``stock_num`` 为单边持仓上限；有效标的不足时取 ``min(stock_num, 有效数)``（long_only）
或 ``min(stock_num, 有效数//2)``（long_short，避免多空持仓重叠）。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from app.services.data.calendar import PandasCalendar
from app.services.portfolio.grouping import rank_groups
from app.services.data.calendar import ICalendar
from app.services.strategy.vectorized.interfaces import IStrategy
from app.models.strategy import BacktestSignals
from app.models.data import Panel


class FactorQuantileStrategy(IStrategy):
    """因子分位组合策略（向量化信号模式）。"""

    name: str = "factor_quantile"

    def __init__(
        self,
        factor_values: pd.DataFrame,
        close: pd.DataFrame,
        rebalance: str = "monthly",
        stock_num: int = 100,
        long_short: bool = True,
        calendar: Optional[ICalendar] = None,
        weight_by: Optional[pd.DataFrame] = None,
    ) -> None:
        self._factor_values = factor_values
        self._close = close
        self._rebalance = rebalance
        self._stock_num = int(stock_num)
        self._long_short = bool(long_short)
        self._calendar = calendar or PandasCalendar()
        # 自定义权重：与 factor_values 同形的 DataFrame，选中的股票按其值比例加权
        # 如 weight_by = current_mv 可实现市值加权
        self._weight_by = weight_by

    def generate_signals(self, panel: Optional[Panel] = None) -> BacktestSignals:
        fv0 = self._factor_values
        close0 = self._close

        # 对齐（与 build_factor_portfolio 逐位一致）
        common_dates = fv0.index.intersection(close0.index)
        common_symbols = fv0.columns.intersection(close0.columns)
        fv = fv0.loc[common_dates, common_symbols]
        close = close0.loc[common_dates, common_symbols]

        reb_mask = self._calendar.rebalance_mask(fv.index, self._rebalance)

        valid = fv.notna()                              # (T, N)
        n_per_day = valid.sum(axis=1)                   # (T,)
        if self._long_short:
            n_side = np.minimum(self._stock_num, n_per_day // 2)
        else:
            n_side = np.minimum(self._stock_num, n_per_day)
        ranks = fv.where(valid).rank(axis=1, ascending=False, method="first")
        ranks_np = ranks.to_numpy()
        n_side_np = n_side.to_numpy()[:, None].astype(np.int64)
        npd_np = n_per_day.to_numpy()[:, None].astype(np.int64)
        valid_np = valid.to_numpy().astype(bool)
        active = ((reb_mask.to_numpy() & (n_side.to_numpy() > 0)).astype(bool))[:, None]
        top_mask = (ranks_np <= n_side_np) & valid_np
        top_mask = top_mask & active
        bottom_mask = (ranks_np > (npd_np - n_side_np)) & valid_np
        bottom_mask = bottom_mask & active
        inv_side = 1.0 / np.maximum(n_side_np, 1)       # active 已排除 n_side=0

        # 是否使用自定义权重（如市值加权）
        use_custom_weight = self._weight_by is not None
        if use_custom_weight:
            wb = self._weight_by.loc[common_dates, common_symbols].to_numpy()
            # 每行内按 top_mask/bottom_mask 做比例加权
            wb_sum = np.where(top_mask, wb, 0.0).sum(axis=1, keepdims=True)
            wb_top = np.where(top_mask & (wb_sum > 0), wb / np.maximum(wb_sum, 1e-10), 0.0)
            if self._long_short:
                wb_sum_b = np.where(bottom_mask, wb, 0.0).sum(axis=1, keepdims=True)
                wb_bottom = np.where(bottom_mask & (wb_sum_b > 0), -wb / np.maximum(wb_sum_b, 1e-10), 0.0)
            else:
                wb_bottom = np.zeros_like(wb)

        target_np = np.where(active & valid_np, 0.0, np.nan)
        if use_custom_weight:
            target_np = np.where(top_mask, wb_top, target_np)
            if self._long_short:
                target_np = np.where(bottom_mask, wb_bottom, target_np)
        else:
            target_np = target_np + np.where(top_mask, inv_side, 0.0)
            if self._long_short:
                target_np = target_np + np.where(bottom_mask, -inv_side, 0.0)
        target = pd.DataFrame(target_np, index=fv.index, columns=fv.columns)

        return BacktestSignals(target_weights=target, close=close)


class FactorGroupStrategy(IStrategy):
    """因子分层策略：持有最高组，或最高组对冲最低组。"""

    name: str = "factor_group"

    def __init__(
        self,
        factor_values: pd.DataFrame,
        close: pd.DataFrame,
        groups: int = 5,
        rebalance_days: int = 20,
        long_short: bool = True,
        calendar: Optional[ICalendar] = None,
        group_assignments: Optional[pd.DataFrame] = None,
    ) -> None:
        if groups < 2:
            raise ValueError(f"groups 至少为 2，得到 {groups}")
        self._factor_values = factor_values
        self._close = close
        self._groups = int(groups)
        self._rebalance_days = int(rebalance_days)
        self._long_short = bool(long_short)
        self._calendar = calendar or PandasCalendar()
        self._group_assignments = group_assignments

    def generate_signals(self, panel: Optional[Panel] = None) -> BacktestSignals:
        common_dates = self._factor_values.index.intersection(self._close.index)
        common_symbols = self._factor_values.columns.intersection(self._close.columns)
        fv = self._factor_values.loc[common_dates, common_symbols]
        close = self._close.loc[common_dates, common_symbols]

        # 使用公共 rank 分组，保证策略与分层分析使用完全相同的成员。
        if self._group_assignments is None:
            group_no = rank_groups(fv, self._groups)
        else:
            group_no = self._group_assignments.reindex(
                index=fv.index, columns=fv.columns
            )
        valid = group_no.notna()
        top = (group_no == 1) & valid
        bottom = (group_no == self._groups) & valid
        rebalance = self._calendar.rebalance_mask(fv.index, self._rebalance_days)

        top_count = top.sum(axis=1).replace(0, np.nan)
        target = top.div(top_count, axis=0)
        if self._long_short:
            bottom_count = bottom.sum(axis=1).replace(0, np.nan)
            target = target.sub(bottom.div(bottom_count, axis=0), fill_value=0.0)
        target = target.fillna(0.0).where(rebalance, np.nan)
        return BacktestSignals(target_weights=target, close=close)
