"""亚历山大·埃尔德强力指数（Force Index）A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class ElderForceIndexAShareEventStrategy:
    """强力指数上穿零轴且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "volume"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        force_window: int = 13,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.force_window = force_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"强力指数策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close", "volume"],
            max(self.force_window, self.trend_window) + 3,
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
        minimum = max(self.force_window, self.trend_window) + 1
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum + 1:
                continue
            force = self._force_index(
                bars["close"], bars["volume"], self.force_window
            )
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([force.iloc[-2], force.iloc[-1], trend.iloc[-1]]).any():
                continue
            average_volume = bars["volume"].tail(self.force_window).mean()
            if pd.isna(average_volume) or average_volume <= 0:
                continue
            close = float(bars["close"].iloc[-1])
            normalized_force = float(force.iloc[-1] / average_volume)
            result[symbol] = {
                "close": close,
                "entry": bool(
                    force.iloc[-2] <= 0
                    and force.iloc[-1] > 0
                    and close > trend.iloc[-1]
                ),
                "exit": bool(force.iloc[-1] < 0 or close < trend.iloc[-1]),
                "score": normalized_force,
            }
        return result

    @staticmethod
    def _force_index(
        close: pd.Series,
        volume: pd.Series,
        window: int = 13,
    ) -> pd.Series:
        raw_force = close.diff() * volume
        return raw_force.ewm(span=window, adjust=False, min_periods=window).mean()
