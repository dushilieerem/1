"""TRIX 三重指数平滑 A 股日频动量策略。"""

from __future__ import annotations

import pandas as pd


class TrixMomentumAShareEventStrategy:
    """TRIX 上穿信号线且位于零轴上方时做多的现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        trix_window: int = 15,
        signal_window: int = 9,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.trix_window = trix_window
        self.signal_window = signal_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"TRIX 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            self.trend_window + self.trix_window * 3 + self.signal_window + 3,
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
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            minimum = self.trend_window + self.trix_window * 3 + self.signal_window
            if len(bars) < minimum + 2:
                continue
            trix, signal = self._trix(bars["close"], self.trix_window, self.signal_window)
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([trix.iloc[-2], trix.iloc[-1], signal.iloc[-2], signal.iloc[-1], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    trix.iloc[-2] <= signal.iloc[-2]
                    and trix.iloc[-1] > signal.iloc[-1]
                    and trix.iloc[-1] > 0
                    and close > trend.iloc[-1]
                ),
                "exit": bool(
                    trix.iloc[-1] < signal.iloc[-1]
                    or trix.iloc[-1] < 0
                    or close < trend.iloc[-1]
                ),
                "score": float(trix.iloc[-1] - signal.iloc[-1]),
            }
        return result

    @staticmethod
    def _trix(
        close: pd.Series, window: int = 15, signal_window: int = 9
    ) -> tuple[pd.Series, pd.Series]:
        first = close.ewm(span=window, adjust=False, min_periods=window).mean()
        second = first.ewm(span=window, adjust=False, min_periods=window).mean()
        third = second.ewm(span=window, adjust=False, min_periods=window).mean()
        trix = third.pct_change() * 100.0
        signal = trix.ewm(span=signal_window, adjust=False, min_periods=signal_window).mean()
        return trix, signal
