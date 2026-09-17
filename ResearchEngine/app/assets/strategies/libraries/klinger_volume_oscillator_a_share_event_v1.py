"""Klinger Volume Oscillator A 股日频现金多头研究策略。"""

from __future__ import annotations

import pandas as pd


class KlingerVolumeOscillatorAShareEventStrategy:
    """以方向化成交量力量和 Klinger 振荡器确认趋势的日频策略。"""

    execution_mode = "event"
    required_fields = frozenset({"high", "low", "close", "volume"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        fast_window: int = 34,
        slow_window: int = 55,
        signal_window: int = 13,
        trend_window: int = 55,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.signal_window = signal_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Klinger A 股策略缺少数据字段: {sorted(missing)}")
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
        lookback = max(self.slow_window, self.trend_window) + self.signal_window + 20
        history = context.data.history(
            symbols, ["high", "low", "close", "volume"], lookback
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
        minimum = max(self.slow_window, self.trend_window) + self.signal_window + 2
        for symbol in symbols:
            bars = pd.DataFrame(
                {field: history[field][symbol] for field in history}
            ).dropna()
            bars = bars[bars["volume"] > 0]
            if len(bars) < minimum:
                continue
            indicators = self._klinger(
                bars["high"],
                bars["low"],
                bars["close"],
                bars["volume"],
                self.fast_window,
                self.slow_window,
                self.signal_window,
            )
            trend = bars["close"].ewm(
                span=self.trend_window,
                adjust=False,
                min_periods=self.trend_window,
            ).mean()
            values = [
                indicators["ko"].iloc[-2],
                indicators["ko"].iloc[-1],
                indicators["signal"].iloc[-2],
                indicators["signal"].iloc[-1],
                trend.iloc[-1],
            ]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            ko = float(indicators["ko"].iloc[-1])
            signal = float(indicators["signal"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    indicators["ko"].iloc[-2] <= indicators["signal"].iloc[-2]
                    and ko > signal
                    and close > trend.iloc[-1]
                ),
                "exit": bool(ko < signal or close < trend.iloc[-1]),
                "score": float(
                    (ko - signal)
                    / max(float(bars["volume"].iloc[-20:].mean()), 1.0)
                ),
            }
        return result

    @staticmethod
    def _klinger(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
        fast_window: int = 34,
        slow_window: int = 55,
        signal_window: int = 13,
    ) -> pd.DataFrame:
        typical = (high + low + close) / 3.0
        direction = typical.diff().ge(0).astype(float).replace(0.0, -1.0)
        direction.iloc[0] = 0.0
        daily_measure = (high - low).abs()
        cumulative_measure = daily_measure.ewm(
            span=slow_window, adjust=False, min_periods=slow_window
        ).mean()
        ratio = daily_measure / cumulative_measure.where(cumulative_measure > 0)
        volume_force = direction * volume * (2.0 * ratio - 1.0).abs()
        fast = volume_force.ewm(
            span=fast_window, adjust=False, min_periods=fast_window
        ).mean()
        slow = volume_force.ewm(
            span=slow_window, adjust=False, min_periods=slow_window
        ).mean()
        ko = fast - slow
        signal = ko.ewm(
            span=signal_window, adjust=False, min_periods=signal_window
        ).mean()
        return pd.DataFrame({"ko": ko, "signal": signal}, index=close.index)
