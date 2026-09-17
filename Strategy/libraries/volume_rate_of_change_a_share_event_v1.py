"""VROC 成交量变动速率 A 股日频现金多头研究策略。"""

from __future__ import annotations

import pandas as pd


class VolumeRateOfChangeAShareEventStrategy:
    """以成交量变动速率和长期价格趋势过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close", "volume"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        volume_window: int = 12,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.volume_window = volume_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"VROC A 股策略缺少数据字段: {sorted(missing)}")
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
        lookback = max(self.volume_window, self.trend_window) + 8
        history = context.data.history(symbols, ["close", "volume"], lookback)
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
        minimum = max(self.volume_window, self.trend_window) + 2
        for symbol in symbols:
            raw = pd.DataFrame(
                {field: history[field][symbol] for field in history}
            )
            if (
                raw.empty
                or raw.iloc[-1].isna().any()
                or raw["close"].iloc[-1] <= 0
                or raw["volume"].iloc[-1] <= 0
            ):
                continue
            bars = raw.dropna()
            bars = bars[bars["volume"] > 0]
            if len(bars) < minimum:
                continue
            vroc = self._vroc(bars["volume"], self.volume_window)
            trend = bars["close"].rolling(
                self.trend_window, min_periods=self.trend_window
            ).mean()
            values = [vroc.iloc[-2], vroc.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            vroc_value = float(vroc.iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    vroc.iloc[-2] <= 0.0
                    and vroc_value > 0.0
                    and close > trend.iloc[-1]
                ),
                "exit": bool(vroc_value < 0.0 or close < trend.iloc[-1]),
                "score": float(vroc_value / 100.0),
            }
        return result

    @staticmethod
    def _vroc(volume: pd.Series, window: int = 12) -> pd.Series:
        """返回成交量相对窗口前的百分比变化。"""
        return volume.pct_change(window) * 100.0
