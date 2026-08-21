"""Pivot Point 支撑阻力突破 A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class PivotPointBreakoutAShareEventStrategy:
    """使用前一交易日枢轴阻力突破和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Pivot Point 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            self.trend_window + 8,
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
        minimum = self.trend_window + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            levels = self._pivot_levels(bars["high"], bars["low"], bars["close"])
            trend = bars["close"].rolling(
                self.trend_window,
                min_periods=self.trend_window,
            ).mean()
            latest = levels.iloc[-1]
            previous = levels.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna(latest).any() or pd.isna(previous).any() or pd.isna(latest_trend):
                continue
            latest_close = float(bars["close"].iloc[-1])
            resistance = float(latest["resistance"])
            pivot = float(latest["pivot"])
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    bars["close"].iloc[-2] <= previous["resistance"]
                    and latest_close > resistance
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_close < pivot or latest_close < float(latest_trend)
                ),
                "score": float(
                    (latest_close - resistance) / max(abs(resistance), 1e-8)
                ),
            }
        return result

    @staticmethod
    def _pivot_levels(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
    ) -> pd.DataFrame:
        previous_high = high.shift(1)
        previous_low = low.shift(1)
        previous_close = close.shift(1)
        pivot = (previous_high + previous_low + previous_close) / 3.0
        return pd.DataFrame(
            {
                "pivot": pivot,
                "resistance": 2.0 * pivot - previous_low,
                "support": 2.0 * pivot - previous_high,
            },
            index=close.index,
        )
