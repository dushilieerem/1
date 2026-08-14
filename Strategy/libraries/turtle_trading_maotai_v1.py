"""贵州茅台日频海龟交易策略。"""

from __future__ import annotations

import math

import pandas as pd


class TurtleTradingMaotaiStrategy:
    """以 20 日突破入场、10 日低点或 2N 止损离场的单标的海龟策略。"""

    symbol = "600519.SH"
    fixed_symbols = (symbol,)
    entry_window = 20
    exit_window = 10
    atr_window = 20
    risk_fraction = 0.01
    max_units = 4

    required_fields = frozenset({"open", "high", "low", "close"})

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"海龟策略缺少数据字段: {sorted(missing)}")
        if self.symbol not in context.data.symbols:
            raise ValueError(f"海龟策略要求行情包含标的: {self.symbol}")
        context.state.unit_size = 0
        context.state.last_entry_price = None
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        history = context.data.history(
            [self.symbol], ["high", "low", "close"], self.atr_window + 1
        )
        if len(history["close"]) < self.atr_window + 1:
            return

        high = history["high"][self.symbol]
        low = history["low"][self.symbol]
        close = history["close"][self.symbol]
        if high.isna().any() or low.isna().any() or close.isna().any():
            return

        atr = self._atr(high, low, close)
        if not math.isfinite(atr) or atr <= 0:
            return
        current_price = float(close.iloc[-1])
        quantity = context.portfolio.quantity(self.symbol)
        if quantity <= 0:
            context.state.unit_size = 0
            context.state.last_entry_price = None
            if current_price > float(high.iloc[-self.entry_window - 1:-1].max()):
                unit_size = self._unit_size(context.portfolio.cash, atr)
                if unit_size:
                    context.orders.target_quantity(self.symbol, unit_size)
                    context.state.unit_size = unit_size
                    context.state.last_entry_price = current_price
            return

        lower_channel = float(low.iloc[-self.exit_window - 1:-1].min())
        stop_price = context.state.last_entry_price - 2 * atr
        if current_price < lower_channel or current_price < stop_price:
            context.orders.close(self.symbol)
            return

        unit_size = context.state.unit_size
        unit_count = quantity // unit_size if unit_size else self.max_units
        if (
            unit_count < self.max_units
            and current_price >= context.state.last_entry_price + 0.5 * atr
        ):
            context.orders.target_quantity(self.symbol, quantity + unit_size)
            context.state.last_entry_price = current_price

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series) -> float:
        previous_close = close.shift(1)
        true_range = pd.concat(
            [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
            axis=1,
        ).max(axis=1)
        return float(true_range.iloc[-20:].mean())

    def _unit_size(self, cash: float, atr: float) -> int:
        raw_quantity = cash * self.risk_fraction / atr
        return int(raw_quantity // 100) * 100
