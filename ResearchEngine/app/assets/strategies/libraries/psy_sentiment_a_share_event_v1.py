"""PSY 心理线 A 股日频现金多头研究策略。"""

from __future__ import annotations

import pandas as pd


class PsySentimentAShareEventStrategy:
    """以最近上涨交易日占比和长期趋势过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        window: int = 12,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.window = window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"PSY A 股策略缺少数据字段: {sorted(missing)}")
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
        lookback = max(self.window, self.trend_window) + 8
        history = context.data.history(symbols, ["close"], lookback)
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
        minimum = max(self.window, self.trend_window) + 2
        for symbol in symbols:
            raw_close = history["close"][symbol]
            if raw_close.empty or pd.isna(raw_close.iloc[-1]) or raw_close.iloc[-1] <= 0:
                continue
            close = raw_close.dropna()
            if len(close) < minimum:
                continue
            psy = self._psy(close, self.window)
            trend = close.rolling(
                self.trend_window, min_periods=self.trend_window
            ).mean()
            values = [psy.iloc[-2], psy.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close_value = float(close.iloc[-1])
            psy_value = float(psy.iloc[-1])
            result[symbol] = {
                "close": close_value,
                "entry": bool(
                    psy.iloc[-2] <= 50.0
                    and psy_value > 50.0
                    and close_value > trend.iloc[-1]
                ),
                "exit": bool(psy_value < 40.0 or close_value < trend.iloc[-1]),
                "score": float((psy_value - 50.0) / 50.0),
            }
        return result

    @staticmethod
    def _psy(close: pd.Series, window: int = 12) -> pd.Series:
        """返回最近窗口内上涨交易日占比，单位为百分比。"""
        return (close.diff() > 0).rolling(window, min_periods=window).mean() * 100.0
