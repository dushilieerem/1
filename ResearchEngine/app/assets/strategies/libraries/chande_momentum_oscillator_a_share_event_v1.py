"""钱德动量振荡器（CMO）A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class ChandeMomentumOscillatorAShareEventStrategy:
    """CMO 从超卖区回升且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        cmo_window: int = 20,
        trend_window: int = 60,
        entry_threshold: float = -50.0,
        exit_threshold: float = 50.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.cmo_window = cmo_window
        self.trend_window = trend_window
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"CMO 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.cmo_window, self.trend_window) + 3,
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
        minimum = max(self.cmo_window, self.trend_window) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            cmo = self._cmo(bars["close"], self.cmo_window)
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            values = [cmo.iloc[-2], cmo.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    cmo.iloc[-2] <= self.entry_threshold
                    and cmo.iloc[-1] > self.entry_threshold
                    and close > trend.iloc[-1]
                ),
                "exit": bool(
                    cmo.iloc[-1] >= self.exit_threshold
                    or cmo.iloc[-1] < 0
                    or close < trend.iloc[-1]
                ),
                "score": float(cmo.iloc[-1] / 100.0 + close / trend.iloc[-1] - 1.0),
            }
        return result

    @staticmethod
    def _cmo(close: pd.Series, window: int = 20) -> pd.Series:
        delta = close.diff()
        up_sum = delta.clip(lower=0).rolling(window, min_periods=window).sum()
        down_sum = (-delta.clip(upper=0)).rolling(window, min_periods=window).sum()
        return 100.0 * (up_sum - down_sum) / (up_sum + down_sum + 1e-10)
