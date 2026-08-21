"""费舍尔变换 A 股日频策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class FisherTransformAShareEventStrategy:
    """费舍尔变换上穿信号线且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        fisher_window: int = 10,
        signal_window: int = 3,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.fisher_window = fisher_window
        self.signal_window = signal_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Fisher 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            self.trend_window + self.fisher_window + self.signal_window + 5,
        )
        metrics = self._metrics(history, symbols)

        survivors = set()
        for symbol in holdings:
            item = metrics.get(symbol)
            if item is None or item["exit"]:
                context.orders.close(symbol)
            else:
                survivors.add(symbol)

        slots = self.max_holdings - len(survivors)
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
        minimum = self.trend_window + self.fisher_window + self.signal_window
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum + 2:
                continue
            fisher = self._fisher(bars["high"], bars["low"], self.fisher_window)
            signal = fisher.rolling(self.signal_window, min_periods=self.signal_window).mean()
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            values = [fisher.iloc[-2], fisher.iloc[-1], signal.iloc[-2], signal.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    fisher.iloc[-2] <= signal.iloc[-2]
                    and fisher.iloc[-1] > signal.iloc[-1]
                    and fisher.iloc[-1] > 0
                    and close > trend.iloc[-1]
                ),
                "exit": bool(
                    fisher.iloc[-1] < signal.iloc[-1]
                    or fisher.iloc[-1] < 0
                    or close < trend.iloc[-1]
                ),
                "score": float(fisher.iloc[-1] - signal.iloc[-1]),
            }
        return result

    @staticmethod
    def _fisher(high: pd.Series, low: pd.Series, window: int = 10) -> pd.Series:
        midpoint = (high + low) / 2.0
        lowest = midpoint.rolling(window, min_periods=window).min()
        highest = midpoint.rolling(window, min_periods=window).max()
        price_range = highest - lowest
        normalized = (
            2.0 * (midpoint - lowest) / (price_range + 1e-10) - 1.0
        ).where(price_range > 0, 0.0)
        normalized = normalized.clip(-0.999999, 0.999999)
        return 0.5 * np.log((1.0 + normalized) / (1.0 - normalized))
