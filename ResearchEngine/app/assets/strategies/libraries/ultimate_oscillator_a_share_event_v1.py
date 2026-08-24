"""终极振荡器（Ultimate Oscillator）A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class UltimateOscillatorAShareEventStrategy:
    """多周期买压从超卖区回升且长期趋势向上时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        short_window: int = 7,
        medium_window: int = 14,
        long_window: int = 28,
        trend_window: int = 60,
        oversold: float = 30.0,
        overbought: float = 70.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.short_window = short_window
        self.medium_window = medium_window
        self.long_window = long_window
        self.trend_window = trend_window
        self.oversold = oversold
        self.overbought = overbought

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"终极振荡器策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(self.long_window, self.trend_window) + 3,
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
        minimum = max(self.long_window, self.trend_window) + 1
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum + 1:
                continue
            oscillator = self._ultimate_oscillator(
                bars["high"],
                bars["low"],
                bars["close"],
                self.short_window,
                self.medium_window,
                self.long_window,
            )
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([oscillator.iloc[-2], oscillator.iloc[-1], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    oscillator.iloc[-2] <= self.oversold
                    and oscillator.iloc[-1] > self.oversold
                    and close > trend.iloc[-1]
                ),
                "exit": bool(oscillator.iloc[-1] >= self.overbought or close < trend.iloc[-1]),
                "score": float(oscillator.iloc[-1] / 100.0 + close / trend.iloc[-1] - 1.0),
            }
        return result

    @staticmethod
    def _ultimate_oscillator(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        short_window: int = 7,
        medium_window: int = 14,
        long_window: int = 28,
    ) -> pd.Series:
        previous_close = close.shift()
        minimum = low.where(low <= previous_close, previous_close)
        maximum = high.where(high >= previous_close, previous_close)
        buying_pressure = close - minimum
        true_range = maximum - minimum

        def average(window: int) -> pd.Series:
            return buying_pressure.rolling(window).sum() / (
                true_range.rolling(window).sum() + 1e-10
            )

        return 100.0 * (
            4.0 * average(short_window)
            + 2.0 * average(medium_window)
            + average(long_window)
        ) / 7.0
