"""西蒙斯风格配对交易的日频向量化研究策略。"""

from __future__ import annotations

import pandas as pd

from app.models.strategy import BacktestSignals


class SimonsPairsTradingResearchStrategy:
    """按价格比 Z-score 构建等名义多空配对，未模拟借券、保证金和融券成本。"""

    execution_mode = "vectorized"
    pair_symbols = ("600519.SH", "000858.SZ")

    def __init__(
        self,
        close: pd.DataFrame,
        stock_a: str = "600519.SH",
        stock_b: str = "000858.SZ",
        lookback: int = 60,
        entry_zscore: float = 1.5,
        exit_zscore: float = 0.5,
        stop_zscore: float = 3.0,
    ) -> None:
        self.close = close
        self.stock_a = stock_a
        self.stock_b = stock_b
        self.lookback = lookback
        self.entry_zscore = entry_zscore
        self.exit_zscore = exit_zscore
        self.stop_zscore = stop_zscore

    def generate_signals(self) -> BacktestSignals:
        missing = {self.stock_a, self.stock_b} - set(self.close.columns)
        if missing:
            raise ValueError(f"配对交易策略缺少收盘价: {sorted(missing)}")
        ratio = self.close[self.stock_a] / self.close[self.stock_b]
        mean = ratio.rolling(self.lookback, min_periods=self.lookback).mean()
        std = ratio.rolling(self.lookback, min_periods=self.lookback).std(ddof=0)
        zscore = (ratio - mean) / std.replace(0, float("nan"))

        target = pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)
        position = 0
        for date, value in zscore.items():
            if pd.isna(value):
                continue
            if position and (abs(value) < self.exit_zscore or abs(value) > self.stop_zscore):
                position = 0
            elif position == 0 and value > self.entry_zscore:
                position = -1
            elif position == 0 and value < -self.entry_zscore:
                position = 1
            if position == 1:
                target.at[date, self.stock_a] = 0.5
                target.at[date, self.stock_b] = -0.5
            elif position == -1:
                target.at[date, self.stock_a] = -0.5
                target.at[date, self.stock_b] = 0.5
        return BacktestSignals(target_weights=target, close=self.close)
