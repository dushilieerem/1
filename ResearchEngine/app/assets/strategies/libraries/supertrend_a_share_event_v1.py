"""Supertrend A 股日频趋势策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class SupertrendAShareEventStrategy:
    """以 ATR 波动带识别趋势反转，并用长期均线过滤现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        atr_window: int = 10,
        multiplier: float = 3.0,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.atr_window = atr_window
        self.multiplier = multiplier
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Supertrend 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(self.trend_window, self.atr_window + 2) + 5,
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
        minimum = max(self.trend_window, self.atr_window) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            indicator = self._supertrend(
                bars["high"],
                bars["low"],
                bars["close"],
                self.atr_window,
                self.multiplier,
            )
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest = indicator.iloc[-1]
            previous = indicator.iloc[-2]
            if pd.isna([latest["direction"], previous["direction"], latest["supertrend"], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            supertrend = float(latest["supertrend"])
            direction = float(latest["direction"])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    previous["direction"] <= 0
                    and direction > 0
                    and close > float(trend.iloc[-1])
                ),
                "exit": bool(direction < 0 or close < float(trend.iloc[-1])),
                "score": float(close / max(abs(supertrend), 1e-8) - 1),
            }
        return result

    @staticmethod
    def _supertrend(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        atr_window: int = 10,
        multiplier: float = 3.0,
    ) -> pd.DataFrame:
        previous_close = close.shift()
        true_range = pd.concat(
            [
                high - low,
                (high - previous_close).abs(),
                (low - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = true_range.ewm(
            alpha=1 / atr_window,
            adjust=False,
            min_periods=atr_window,
        ).mean()
        midpoint = (high + low) / 2
        basic_upper = midpoint + multiplier * atr
        basic_lower = midpoint - multiplier * atr
        final_upper = pd.Series(np.nan, index=close.index, dtype=float)
        final_lower = pd.Series(np.nan, index=close.index, dtype=float)
        direction = pd.Series(np.nan, index=close.index, dtype=float)
        supertrend = pd.Series(np.nan, index=close.index, dtype=float)

        valid_positions = np.flatnonzero(basic_upper.notna().to_numpy())
        if len(valid_positions) == 0:
            return pd.DataFrame(
                {
                    "atr": atr,
                    "upper": final_upper,
                    "lower": final_lower,
                    "direction": direction,
                    "supertrend": supertrend,
                }
            )
        first = int(valid_positions[0])
        for position in range(first, len(close)):
            if position == first:
                final_upper.iloc[position] = basic_upper.iloc[position]
                final_lower.iloc[position] = basic_lower.iloc[position]
                direction.iloc[position] = 1.0
                supertrend.iloc[position] = final_lower.iloc[position]
                continue

            previous_upper = final_upper.iloc[position - 1]
            previous_lower = final_lower.iloc[position - 1]
            final_upper.iloc[position] = (
                basic_upper.iloc[position]
                if basic_upper.iloc[position] < previous_upper
                or close.iloc[position - 1] > previous_upper
                else previous_upper
            )
            final_lower.iloc[position] = (
                basic_lower.iloc[position]
                if basic_lower.iloc[position] > previous_lower
                or close.iloc[position - 1] < previous_lower
                else previous_lower
            )
            if close.iloc[position] > previous_upper:
                direction.iloc[position] = 1.0
            elif close.iloc[position] < previous_lower:
                direction.iloc[position] = -1.0
            else:
                direction.iloc[position] = direction.iloc[position - 1]
            supertrend.iloc[position] = (
                final_lower.iloc[position]
                if direction.iloc[position] > 0
                else final_upper.iloc[position]
            )

        return pd.DataFrame(
            {
                "atr": atr,
                "upper": final_upper,
                "lower": final_lower,
                "direction": direction,
                "supertrend": supertrend,
            }
        )
