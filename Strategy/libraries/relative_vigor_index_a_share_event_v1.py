"""相对活力指数（RVI）A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class RelativeVigorIndexAShareEventStrategy:
    """RVI 上穿信号线且长期趋势向上时做多的现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        rvi_window: int = 10,
        signal_window: int = 4,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.rvi_window = rvi_window
        self.signal_window = signal_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"RVI 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["open", "high", "low", "close"],
            self.trend_window + self.rvi_window + self.signal_window + 6,
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
        minimum = self.trend_window + self.rvi_window + self.signal_window + 4
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum + 1:
                continue
            rvi = self._rvi(
                bars["open"],
                bars["high"],
                bars["low"],
                bars["close"],
                self.rvi_window,
            )
            signal = rvi.rolling(self.signal_window, min_periods=self.signal_window).mean()
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            values = [rvi.iloc[-2], rvi.iloc[-1], signal.iloc[-2], signal.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    rvi.iloc[-2] <= signal.iloc[-2]
                    and rvi.iloc[-1] > signal.iloc[-1]
                    and rvi.iloc[-1] > 0
                    and close > trend.iloc[-1]
                ),
                "exit": bool(
                    rvi.iloc[-1] < signal.iloc[-1]
                    or rvi.iloc[-1] < 0
                    or close < trend.iloc[-1]
                ),
                "score": float(rvi.iloc[-1] - signal.iloc[-1]),
            }
        return result

    @staticmethod
    def _rvi(
        open_price: pd.Series,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 10,
    ) -> pd.Series:
        close_open = close - open_price
        high_low = high - low
        numerator = (
            close_open
            + 2 * close_open.shift(1)
            + 2 * close_open.shift(2)
            + close_open.shift(3)
        ) / 6.0
        denominator = (
            high_low
            + 2 * high_low.shift(1)
            + 2 * high_low.shift(2)
            + high_low.shift(3)
        ) / 6.0
        return numerator.rolling(window).mean() / (
            denominator.rolling(window).mean() + 1e-10
        )
