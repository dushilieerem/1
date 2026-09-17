"""因子回测组合引擎。

该模块只把因子截面转换为目标权重、持仓和评价所需的远期收益，不依赖
``BacktestSignals``、``FactorQuantileStrategy`` 或具体回测后端。策略回测
仍可继续使用适配层中的旧信号协议。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.data.calendar import PandasCalendar
from app.services.portfolio.grouping import rank_groups
from app.services.portfolio.records import rebalance_logs_from_targets


class PortfolioEngine:
    """构造因子组合及其共同分组数据。"""

    def __init__(self, *, calendar: PandasCalendar | None = None) -> None:
        self.calendar = calendar or PandasCalendar()

    @staticmethod
    def _align(
        factor_values: pd.DataFrame,
        close: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        dates = factor_values.index.intersection(close.index)
        symbols = factor_values.columns.intersection(close.columns)
        if dates.empty or symbols.empty:
            return pd.DataFrame(), pd.DataFrame()
        return (
            factor_values.loc[dates, symbols].copy(),
            close.loc[dates, symbols].copy(),
        )

    def _rebalance(self, index: pd.DatetimeIndex, rebalance: str | int) -> pd.Series:
        return self.calendar.rebalance_mask(index, rebalance)

    @staticmethod
    def _top_bottom_targets(
        values: pd.DataFrame,
        rebalance_mask: pd.Series,
        *,
        portfolio_type: str,
        stock_num: int,
    ) -> pd.DataFrame:
        valid = values.notna()
        count = valid.sum(axis=1)
        if portfolio_type == "long_short":
            side_count = np.minimum(int(stock_num), count // 2)
        else:
            side_count = np.minimum(int(stock_num), count)
        ranks = values.rank(axis=1, ascending=False, method="first")
        side = side_count.to_numpy(dtype=np.int64)[:, None]
        count_np = count.to_numpy(dtype=np.int64)[:, None]
        valid_np = valid.to_numpy(dtype=bool)
        active = (
            rebalance_mask.to_numpy(dtype=bool)
            & (side_count.to_numpy(dtype=np.int64) > 0)
        )[:, None]
        top = (ranks.to_numpy() <= side) & valid_np & active
        bottom = (ranks.to_numpy() > (count_np - side)) & valid_np & active
        inverse = 1.0 / np.maximum(side, 1)
        target = np.where(active & valid_np, 0.0, np.nan)
        target = target + np.where(top, inverse, 0.0)
        if portfolio_type == "long_short":
            target = target + np.where(bottom, -inverse, 0.0)
        return pd.DataFrame(target, index=values.index, columns=values.columns)

    @staticmethod
    def _group_target(
        groups: pd.DataFrame,
        n_groups: int,
        rebalance_mask: pd.Series,
        *,
        portfolio_type: str,
    ) -> pd.DataFrame:
        """构造主组合目标权重，不展开各分组的完整权重矩阵。"""

        group_values = groups.to_numpy(dtype=float, na_value=np.nan)
        valid = ~np.isnan(group_values)
        top = valid & (group_values == 1)
        bottom = valid & (group_values == n_groups)

        top_count = top.sum(axis=1, dtype=np.int64)
        top_weights = np.divide(
            top,
            np.maximum(top_count, 1)[:, None],
            out=np.zeros_like(group_values, dtype=float),
            where=top_count[:, None] > 0,
        )
        target = top_weights
        if portfolio_type == "long_short":
            bottom_count = bottom.sum(axis=1, dtype=np.int64)
            bottom_weights = np.divide(
                bottom,
                np.maximum(bottom_count, 1)[:, None],
                out=np.zeros_like(group_values, dtype=float),
                where=bottom_count[:, None] > 0,
            )
            target = target - bottom_weights

        rebalance = rebalance_mask.to_numpy(dtype=bool)[:, None]
        target = np.where(rebalance, target, np.nan)
        return pd.DataFrame(target, index=groups.index, columns=groups.columns)

    def build(
        self,
        factor_values: pd.DataFrame,
        close: pd.DataFrame,
        *,
        groups: int | None = 5,
        group_assignments: pd.DataFrame | None = None,
        portfolio_type: str = "long_only",
        rebalance: str | int = 1,
        stock_num: int = 100,
        horizon: int = 1,
        include_rebalance_logs: bool = False,
    ) -> dict[str, Any]:
        """生成组合产物。

        返回映射包含 ``target_weights``、``positions``、``forward_returns``
        和 ``group_assignments``。分组收益所需的等权权重不在这里展开，
        由 MetricEngine 根据分组标签一次性聚合；远期收益在完整收盘价索引
        上先 shift，再与因子对齐，因此不会参与组合选择。完整的
        ``rebalance_logs`` 默认不生成，需要展示逐标的调仓明细时显式传入
        ``include_rebalance_logs=True``。
        """

        if portfolio_type not in {"long_only", "long_short"}:
            raise ValueError(f"不支持的组合类型: {portfolio_type!r}")
        if horizon < 1:
            raise ValueError("远期收益 horizon 至少为 1")
        if stock_num < 1:
            raise ValueError("stock_num 至少为 1")
        # 组合日期只由因子值决定，但远期标签必须先在完整价格索引上
        # shift，再裁剪到因子日期；否则当调用方只传入评价区间时，
        # 区间最后一天会错误地失去区间外可用的 t+h 收盘价。
        full_prices = close.copy()
        values, prices = self._align(factor_values, full_prices)
        if values.empty or prices.empty:
            raise ValueError("因子值与 close 没有共同的日期或标的")

        rebalance_mask = self._rebalance(values.index, rebalance)
        if groups is None:
            assignments = rank_groups(values, 5)
            target = self._top_bottom_targets(
                values,
                rebalance_mask,
                portfolio_type=portfolio_type,
                stock_num=stock_num,
            )
            group_count = None
        else:
            n_groups = int(groups)
            if n_groups < 2:
                raise ValueError("groups 至少为 2")
            assignments = (
                rank_groups(values, n_groups)
                if group_assignments is None
                else group_assignments.reindex(
                    index=values.index, columns=values.columns
                ).copy()
            )
            target = self._group_target(
                assignments,
                n_groups,
                rebalance_mask,
                portfolio_type=portfolio_type,
            )
            group_count = n_groups

        positions = target.ffill().shift(1).fillna(0.0)
        forward = full_prices.loc[:, prices.columns].shift(-int(horizon)).div(
            full_prices.loc[:, prices.columns]
        ).sub(1.0)
        return {
            "factor_values": values,
            "close": prices,
            "target_weights": target,
            "positions": positions,
            "forward_returns": forward.reindex(
                index=values.index, columns=values.columns
            ),
            "group_assignments": assignments,
            # 兼容旧调用方保留字段名，但不再分配 Q1..QN 的 T×N 宽表。
            "group_targets": None,
            "group_count": group_count,
            "rebalance_mask": rebalance_mask,
            "rebalance_logs": (
                self._rebalance_logs(target) if include_rebalance_logs else None
            ),
        }

    def build_portfolio(self, *args, **kwargs) -> dict[str, Any]:
        """语义化别名，供应用层调用。"""

        return self.build(*args, **kwargs)

    @staticmethod
    def _rebalance_logs(target: pd.DataFrame) -> pd.DataFrame:
        """兼容旧私有入口；实际实现集中在 portfolio.records。"""

        return rebalance_logs_from_targets(target)


__all__ = ["PortfolioEngine"]
