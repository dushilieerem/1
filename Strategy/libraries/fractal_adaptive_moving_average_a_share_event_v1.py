"""Fractal Adaptive Moving Average A 股日频现金多头研究策略。"""

from __future__ import annotations

import math

import pandas as pd


class FractalAdaptiveMovingAverageAShareEventStrategy:
    """以分形维度自适应均线和长期趋势过滤的日频现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        window: int = 16,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.window = window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"FRAMA A 股策略缺少数据字段: {sorted(missing)}")
        if self.window < 4 or self.window % 2:
            raise ValueError("FRAMA window 必须为不小于 4 的偶数")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = {
            symbol
            for symbol, quantity in context.portfolio.positions.items()
            if quantity > 0
        }
        symbols = list(
            dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings))
        )
        history = context.data.history(
            symbols, ["close"], max(self.window, self.trend_window) + 10
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
            (
                (symbol, item["score"])
                for symbol, item in metrics.items()
                if symbol not in holdings and item["entry"]
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        for symbol, _ in candidates[:slots]:
            context.orders.target_value(symbol, total_value * self.single_weight)

    def _metrics(self, history, symbols):
        result = {}
        minimum = max(self.window, self.trend_window) + 2
        for symbol in symbols:
            close = history["close"][symbol].dropna()
            if len(close) < minimum:
                continue
            frama = self._frama(close, self.window)
            trend = close.rolling(
                self.trend_window, min_periods=self.trend_window
            ).mean()
            values = [frama.iloc[-2], frama.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close_value = float(close.iloc[-1])
            frama_value = float(frama.iloc[-1])
            result[symbol] = {
                "close": close_value,
                "entry": bool(
                    close.iloc[-2] <= frama.iloc[-2]
                    and close_value > frama_value
                    and frama_value > frama.iloc[-2]
                    and close_value > trend.iloc[-1]
                ),
                "exit": bool(
                    close_value < frama_value
                    or frama_value <= frama.iloc[-2]
                    or close_value < trend.iloc[-1]
                ),
                "score": float(
                    (close_value - frama_value) / max(abs(close_value), 1e-8)
                ),
            }
        return result

    @staticmethod
    def _frama(close: pd.Series, window: int = 16) -> pd.Series:
        """使用两半区间价格范围估计分形维度并递推 FRAMA。"""
        if window < 4 or window % 2:
            raise ValueError("FRAMA window 必须为不小于 4 的偶数")
        half = window // 2
        values = close.astype(float).to_numpy()
        output = [float("nan")] * len(values)
        for index in range(window - 1, len(values)):
            current = values[index]
            if not math.isfinite(current):
                continue
            if index == window - 1 or not math.isfinite(output[index - 1]):
                output[index] = current
                continue
            first = values[index - window + 1 : index - half + 1]
            second = values[index - half + 1 : index + 1]
            if not all(math.isfinite(value) for value in first) or not all(
                math.isfinite(value) for value in second
            ):
                continue
            full = values[index - window + 1 : index + 1]
            n1 = (max(first) - min(first)) / half
            n2 = (max(second) - min(second)) / half
            n3 = (max(full) - min(full)) / window
            if n3 <= 0 or n1 + n2 <= 0:
                alpha = 1.0
            else:
                dimension = math.log(n1 + n2) - math.log(n3)
                dimension /= math.log(2.0)
                alpha = math.exp(-4.6 * (dimension - 1.0))
                alpha = min(1.0, max(0.01, alpha))
            output[index] = alpha * current + (1.0 - alpha) * output[index - 1]
        return pd.Series(output, index=close.index, name=close.name)
