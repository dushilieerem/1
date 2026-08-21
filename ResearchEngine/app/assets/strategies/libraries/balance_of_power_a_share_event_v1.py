"""平衡交易力量（Balance of Power）A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class BalanceOfPowerAShareEventStrategy:
    """平滑 BOP 上穿零轴且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        smooth_window: int = 14,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.smooth_window = smooth_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Balance of Power 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["open", "high", "low", "close"],
            max(self.smooth_window, self.trend_window) + self.smooth_window + 3,
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
            ((symbol, item["score"]) for symbol, item in metrics.items() if symbol not in holdings and item["entry"]),
            key=lambda item: item[1],
            reverse=True,
        )
        for symbol, _ in candidates[:slots]:
            context.orders.target_value(symbol, total_value * self.single_weight)

    def _metrics(self, history, symbols):
        result = {}
        minimum = max(self.smooth_window, self.trend_window) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            power = self._balance_of_power(
                bars["open"], bars["high"], bars["low"], bars["close"]
            )
            smoothed = power.rolling(
                self.smooth_window, min_periods=self.smooth_window
            ).mean()
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([smoothed.iloc[-2], smoothed.iloc[-1], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    smoothed.iloc[-2] <= 0
                    and smoothed.iloc[-1] > 0
                    and close > trend.iloc[-1]
                ),
                "exit": bool(smoothed.iloc[-1] < 0 or close < trend.iloc[-1]),
                "score": float(smoothed.iloc[-1]),
            }
        return result

    @staticmethod
    def _balance_of_power(
        open_: pd.Series,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
    ) -> pd.Series:
        return (close - open_) / (high - low + 1e-10)
