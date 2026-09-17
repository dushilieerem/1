"""Relative Momentum Index A 股日频现金多头研究策略。"""

from __future__ import annotations

import pandas as pd


class RelativeMomentumIndexAShareEventStrategy:
    """以多日动量 RSI 和长期均线过滤趋势的日频现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        momentum_window: int = 5,
        rmi_window: int = 14,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.momentum_window = momentum_window
        self.rmi_window = rmi_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"RMI A 股策略缺少数据字段: {sorted(missing)}")
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
        lookback = self.trend_window + self.momentum_window + self.rmi_window + 5
        history = context.data.history(symbols, ["close"], lookback)
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
        minimum = max(self.trend_window, self.momentum_window + self.rmi_window) + 2
        for symbol in symbols:
            close = history["close"][symbol].dropna()
            if len(close) < minimum:
                continue
            rmi = self._rmi(close, self.momentum_window, self.rmi_window)
            trend = close.rolling(
                self.trend_window, min_periods=self.trend_window
            ).mean()
            values = [rmi.iloc[-2], rmi.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close_value = float(close.iloc[-1])
            rmi_value = float(rmi.iloc[-1])
            result[symbol] = {
                "close": close_value,
                "entry": bool(
                    rmi.iloc[-2] <= 50
                    and rmi_value > 50
                    and close_value > trend.iloc[-1]
                ),
                "exit": bool(rmi_value < 45 or close_value < trend.iloc[-1]),
                "score": float((rmi_value - 50.0) / 50.0),
            }
        return result

    @staticmethod
    def _rmi(
        close: pd.Series,
        momentum_window: int = 5,
        rmi_window: int = 14,
    ) -> pd.Series:
        momentum = close.diff(momentum_window)
        gains = momentum.clip(lower=0.0)
        losses = (-momentum).clip(lower=0.0)
        average_gain = gains.ewm(
            alpha=1 / rmi_window, adjust=False, min_periods=rmi_window
        ).mean()
        average_loss = losses.ewm(
            alpha=1 / rmi_window, adjust=False, min_periods=rmi_window
        ).mean()
        relative_strength = average_gain / average_loss.replace(0.0, float("nan"))
        rmi = 100.0 - 100.0 / (1.0 + relative_strength)
        return rmi.where(average_loss > 0, 100.0)
