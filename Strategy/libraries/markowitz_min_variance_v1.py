"""Markowitz-inspired 最小方差组合研究策略。

仅面向静态股票池的日频向量化研究：使用收盘价、月度调仓和下一交易日生效的目标权重。
不包含动态指数成分、基本面/交易状态过滤或盘中订单执行。
"""

import numpy as np
import pandas as pd

from app.models.strategy import BacktestSignals


class MarkowitzMinVarianceStrategy:
    """以正动量预筛后的历史协方差构建受单股上限约束的最小方差组合。"""

    lookback_days = 120
    momentum_short_days = 60
    candidate_count = 50
    min_assets = 13
    max_single_weight = 0.08
    shrinkage_to_sample = 0.70

    def __init__(self, close: pd.DataFrame) -> None:
        self.close = close

    def generate_signals(self) -> BacktestSignals:
        target = pd.DataFrame(np.nan, index=self.close.index, columns=self.close.columns)
        rebalance_dates = self.close.index.to_series().groupby(
            [self.close.index.year, self.close.index.month], sort=False
        ).head(1).index
        for date in rebalance_dates:
            position = self.close.index.get_loc(date)
            target.loc[date] = self._weights(position)
        return BacktestSignals(target_weights=target, close=self.close)

    def _weights(self, position: int) -> pd.Series:
        empty = pd.Series(0.0, index=self.close.columns)
        if position < self.lookback_days:
            return empty

        prices = self.close.iloc[position - self.lookback_days:position + 1]
        momentum = pd.DataFrame({
            "short": prices.iloc[-1] / prices.iloc[-1 - self.momentum_short_days] - 1.0,
            "long": prices.iloc[-1] / prices.iloc[0] - 1.0,
        }).replace([np.inf, -np.inf], np.nan).dropna()
        candidates = momentum[(momentum["short"] > 0) & (momentum["long"] > 0)]
        candidates = candidates.assign(score=candidates.rank(pct=True).mean(axis=1))
        symbols = candidates.nlargest(self.candidate_count, "score").index
        if len(symbols) < self.min_assets:
            return empty

        returns = prices[symbols].pct_change(fill_method=None).iloc[1:].dropna(axis=1)
        if len(returns.columns) < self.min_assets or len(returns) < self.lookback_days - 1:
            return empty
        covariance = returns.cov().to_numpy() * 252.0
        diagonal = np.diag(np.diag(covariance))
        covariance = self.shrinkage_to_sample * covariance + (1.0 - self.shrinkage_to_sample) * diagonal
        covariance += np.eye(len(returns.columns)) * max(np.median(np.diag(covariance)) * 1e-4, 1e-8)

        raw = np.linalg.pinv(covariance) @ np.ones(len(returns.columns))
        weights = self._project_with_cap(raw)
        if weights is None:
            weights = self._project_with_cap(1.0 / np.sqrt(np.diag(covariance)))
        if weights is None:
            return empty
        empty.loc[returns.columns] = weights
        return empty

    def _project_with_cap(self, raw: np.ndarray) -> np.ndarray | None:
        weights = np.maximum(np.nan_to_num(raw, nan=0.0), 0.0)
        if len(weights) * self.max_single_weight < 1.0 or weights.sum() == 0:
            return None
        result = np.zeros(len(weights))
        active = np.ones(len(weights), dtype=bool)
        remaining = 1.0
        while active.any():
            active_weights = weights[active]
            if active_weights.sum() == 0:
                active_weights = np.ones(active.sum())
            allocation = remaining * active_weights / active_weights.sum()
            indices = np.flatnonzero(active)
            capped = allocation > self.max_single_weight
            if not capped.any():
                result[indices] = allocation
                return result
            result[indices[capped]] = self.max_single_weight
            active[indices[capped]] = False
            remaining = 1.0 - result.sum()
        return None
