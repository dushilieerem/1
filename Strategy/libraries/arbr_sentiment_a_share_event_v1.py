"""ARBR 人气意愿指标 A 股日频现金多头研究策略。"""

from __future__ import annotations

import pandas as pd


class ArbrSentimentAShareEventStrategy:
    """以 ARBR 人气与意愿差值确认趋势的日频现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        window: int = 26,
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
            raise ValueError(f"ARBR A 股策略缺少数据字段: {sorted(missing)}")
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
        history = context.data.history(
            symbols, ["open", "high", "low", "close"], lookback
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
        minimum = max(self.window, self.trend_window) + 2
        for symbol in symbols:
            raw = pd.DataFrame(
                {field: history[field][symbol] for field in history}
            )
            if raw.empty or raw.iloc[-1].isna().any():
                continue
            bars = raw.dropna()
            if len(bars) < minimum:
                continue
            indicators = self._arbr(
                bars["open"], bars["high"], bars["low"], bars["close"], self.window
            )
            trend = bars["close"].rolling(
                self.trend_window, min_periods=self.trend_window
            ).mean()
            values = [
                indicators["arbr"].iloc[-2],
                indicators["arbr"].iloc[-1],
                indicators["ar"].iloc[-1],
                trend.iloc[-1],
            ]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            if close <= 0:
                continue
            arbr = float(indicators["arbr"].iloc[-1])
            ar = float(indicators["ar"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    indicators["arbr"].iloc[-2] <= 0
                    and arbr > 0
                    and ar > 100
                    and close > trend.iloc[-1]
                ),
                "exit": bool(arbr < 0 or close < trend.iloc[-1]),
                "score": float(arbr / 100.0 + (ar - 100.0) / 100.0),
            }
        return result

    @staticmethod
    def _arbr(
        open_: pd.Series,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 26,
    ) -> pd.DataFrame:
        """返回与情绪因子库一致的 AR、BR 和 ARBR 指标。"""
        ar_numerator = (high - open_).rolling(window, min_periods=window).sum()
        ar_denominator = (open_ - low).rolling(window, min_periods=window).sum()
        ar = 100.0 * ar_numerator / ar_denominator.where(ar_denominator > 0)

        previous_close = close.shift()
        br_up = (high - previous_close).clip(lower=0.0)
        br_down = (previous_close - low).clip(lower=0.0)
        br_numerator = br_up.rolling(window, min_periods=window).sum()
        br_denominator = br_down.rolling(window, min_periods=window).sum()
        br = 100.0 * br_numerator / br_denominator.where(br_denominator > 0)
        return pd.DataFrame(
            {"ar": ar, "br": br, "arbr": ar - br},
            index=close.index,
        )
