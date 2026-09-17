"""变化率（ROC）A 股日频动量策略。"""

from __future__ import annotations

import pandas as pd


class RateOfChangeMomentumAShareEventStrategy:
    """ROC 上穿零轴且价格位于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        roc_window: int = 20,
        trend_window: int = 60,
        entry_threshold: float = 0.0,
        exit_threshold: float = 0.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.roc_window = roc_window
        self.trend_window = trend_window
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"ROC 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(self.roc_window, self.trend_window) + self.roc_window + 3,
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
            if len(bars) < max(self.roc_window, self.trend_window) + 2:
                continue
            roc = self._roc(bars["close"], self.roc_window)
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([roc.iloc[-2], roc.iloc[-1], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    roc.iloc[-2] <= self.entry_threshold
                    and roc.iloc[-1] > self.entry_threshold
                    and close > trend.iloc[-1]
                ),
                "exit": bool(roc.iloc[-1] <= self.exit_threshold or close < trend.iloc[-1]),
                "score": float(roc.iloc[-1]),
            }
        return result

    @staticmethod
    def _roc(close: pd.Series, window: int = 20) -> pd.Series:
        return (close / close.shift(window) - 1.0) * 100.0
