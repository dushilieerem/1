"""混沌指标（Choppiness Index）A 股趋势突破策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ChoppinessBreakoutAShareEventStrategy:
    """低混沌环境中突破前高时做多，市场重回震荡时退出。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        choppiness_window: int = 14,
        breakout_window: int = 20,
        trend_window: int = 60,
        entry_threshold: float = 38.2,
        exit_threshold: float = 61.8,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.choppiness_window = choppiness_window
        self.breakout_window = breakout_window
        self.trend_window = trend_window
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Choppiness Index 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(self.choppiness_window, self.breakout_window, self.trend_window) + 3,
        )
        metrics = self._metrics(history, symbols)

        survivors = set()
        for symbol in holdings:
            item = metrics.get(symbol)
            if item is None or item["exit"]:
                context.orders.close(symbol)
            else:
                survivors.add(symbol)

        slots = self.max_holdings - len(holdings)
        if slots <= 0:
            return
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(symbol) * metrics[symbol]["close"]
            for symbol in survivors
        )
        candidates = sorted(
            ((symbol, item["score"]) for symbol, item in metrics.items() if symbol not in holdings and item["entry"]),
            key=lambda item: item[1],
            reverse=True,
        )
        for symbol, _ in candidates[:slots]:
            context.orders.target_value(symbol, total_value * self.single_weight)

    def _metrics(self, history, symbols):
        result = {}
        minimum = max(self.choppiness_window, self.breakout_window, self.trend_window) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            choppiness = self._choppiness_index(
                bars["high"], bars["low"], bars["close"], self.choppiness_window
            )
            prior_high = bars["close"].shift(1).rolling(
                self.breakout_window, min_periods=self.breakout_window
            ).max()
            prior_low = bars["close"].shift(1).rolling(
                self.breakout_window, min_periods=self.breakout_window
            ).min()
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            values = [choppiness.iloc[-1], prior_high.iloc[-1], prior_low.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    choppiness.iloc[-1] < self.entry_threshold
                    and close > prior_high.iloc[-1]
                    and close > trend.iloc[-1]
                ),
                "exit": bool(
                    choppiness.iloc[-1] > self.exit_threshold
                    or close < prior_low.iloc[-1]
                    or close < trend.iloc[-1]
                ),
                "score": float(
                    close / prior_high.iloc[-1] - 1.0
                    + (self.entry_threshold - choppiness.iloc[-1]) / 100.0
                ),
            }
        return result

    @staticmethod
    def _choppiness_index(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 14,
    ) -> pd.Series:
        previous_close = close.shift()
        true_range = pd.concat(
            [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
            axis=1,
        ).max(axis=1)
        true_range_sum = true_range.rolling(window, min_periods=window).sum()
        price_range = high.rolling(window, min_periods=window).max() - low.rolling(
            window, min_periods=window
        ).min()
        ratio = (true_range_sum / (price_range + 1e-10)).clip(lower=1e-10)
        return 100.0 * np.log10(ratio) / np.log10(window)
