"""科波克曲线（Coppock Curve）A 股日频策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class CoppockCurveAShareEventStrategy:
    """科波克曲线上穿零轴且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        short_window: int = 11,
        long_window: int = 14,
        smooth_window: int = 10,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.short_window = short_window
        self.long_window = long_window
        self.smooth_window = smooth_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Coppock Curve 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.long_window + self.smooth_window, self.trend_window) + 3,
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
        minimum = max(self.long_window + self.smooth_window, self.trend_window) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            curve = self._coppock_curve(
                bars["close"], self.short_window, self.long_window, self.smooth_window
            )
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([curve.iloc[-2], curve.iloc[-1], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    curve.iloc[-2] <= 0
                    and curve.iloc[-1] > 0
                    and close > trend.iloc[-1]
                ),
                "exit": bool(curve.iloc[-1] < 0 or close < trend.iloc[-1]),
                "score": float(curve.iloc[-1] / 100.0 + close / trend.iloc[-1] - 1.0),
            }
        return result

    @staticmethod
    def _coppock_curve(
        close: pd.Series,
        short: int = 11,
        long: int = 14,
        smooth: int = 10,
    ) -> pd.Series:
        rate_of_change = close.pct_change(short) * 100.0 + close.pct_change(long) * 100.0
        weights = np.arange(1, smooth + 1, dtype=float)
        return rate_of_change.rolling(smooth, min_periods=smooth).apply(
            lambda values: np.dot(values, weights) / weights.sum(),
            raw=True,
        )
