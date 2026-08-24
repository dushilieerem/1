"""Vortex Indicator 涡旋指标 A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class VortexIndicatorAShareEventStrategy:
    """VI+ 上穿 VI- 且长期趋势向上时做多的现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        vortex_window: int = 14,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.vortex_window = vortex_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Vortex 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(self.vortex_window, self.trend_window) + 3,
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
        minimum = max(self.vortex_window, self.trend_window) + 1
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum + 1:
                continue
            vi_plus, vi_minus = self._vortex(
                bars["high"], bars["low"], bars["close"], self.vortex_window
            )
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([vi_plus.iloc[-2], vi_plus.iloc[-1], vi_minus.iloc[-2], vi_minus.iloc[-1], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    vi_plus.iloc[-2] <= vi_minus.iloc[-2]
                    and vi_plus.iloc[-1] > vi_minus.iloc[-1]
                    and close > trend.iloc[-1]
                ),
                "exit": bool(
                    vi_plus.iloc[-1] < vi_minus.iloc[-1]
                    or close < trend.iloc[-1]
                ),
                "score": float(vi_plus.iloc[-1] - vi_minus.iloc[-1]),
            }
        return result

    @staticmethod
    def _vortex(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 14,
    ) -> tuple[pd.Series, pd.Series]:
        previous_close = close.shift()
        true_range = pd.concat(
            [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
            axis=1,
        ).max(axis=1)
        positive_movement = (high - low.shift()).abs()
        negative_movement = (low - high.shift()).abs()
        true_range_sum = true_range.rolling(window).sum().replace(0, float("nan"))
        return (
            positive_movement.rolling(window).sum() / true_range_sum,
            negative_movement.rolling(window).sum() / true_range_sum,
        )
