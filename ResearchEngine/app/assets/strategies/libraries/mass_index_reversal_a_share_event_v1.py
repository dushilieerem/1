"""Mass Index 梅斯线 A 股日频波动反转策略。"""

from __future__ import annotations

import pandas as pd


class MassIndexReversalAShareEventStrategy:
    """捕捉区间扩张后 Mass Index 回落的现金多头反转信号。"""

    execution_mode = "event"
    required_fields = frozenset({"high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        short_window: int = 9,
        long_window: int = 25,
        trend_window: int = 60,
        peak_level: float = 27.0,
        reversal_level: float = 26.5,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.short_window = short_window
        self.long_window = long_window
        self.trend_window = trend_window
        self.peak_level = peak_level
        self.reversal_level = reversal_level

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Mass Index 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(self.trend_window, 2 * self.short_window + self.long_window) + 8,
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
        minimum = max(self.trend_window, 2 * self.short_window + self.long_window) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            high = bars["high"]
            low = bars["low"]
            close = bars["close"]
            mass = self._mass_index(high, low, self.short_window, self.long_window)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_mass = mass.iloc[-1]
            previous_mass = mass.iloc[-2]
            latest_trend = trend.iloc[-1]
            recent_peak = mass.iloc[-max(self.long_window, 10):-1].max()
            if pd.isna([latest_mass, previous_mass, latest_trend, recent_peak]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_mass = float(latest_mass)
            previous_mass = float(previous_mass)
            latest_trend = float(latest_trend)
            recent_peak = float(recent_peak)
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    previous_mass >= self.reversal_level
                    and latest_mass < self.reversal_level
                    and recent_peak >= self.peak_level
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_mass >= self.peak_level
                    or latest_close < latest_trend
                ),
                "score": float(
                    (latest_close - latest_trend) / max(abs(latest_trend), 1e-8)
                    + (self.reversal_level - latest_mass)
                ),
            }
        return result

    @staticmethod
    def _mass_index(
        high: pd.Series,
        low: pd.Series,
        short_window: int = 9,
        long_window: int = 25,
    ) -> pd.Series:
        spread = high - low
        first_average = spread.rolling(short_window, min_periods=short_window).mean()
        second_average = first_average.rolling(short_window, min_periods=short_window).mean()
        ratio = first_average / second_average.where(second_average.ne(0))
        return ratio.rolling(long_window, min_periods=long_window).sum()
