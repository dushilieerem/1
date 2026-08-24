"""Ulcer Index 低回撤 A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class UlcerIndexLowDrawdownAShareEventStrategy:
    """使用 Ulcer Index 回落和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        ulcer_window: int = 14,
        trend_window: int = 60,
        entry_threshold: float = 5.0,
        exit_threshold: float = 10.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.ulcer_window = ulcer_window
        self.trend_window = trend_window
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Ulcer Index 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = {
            symbol for symbol, quantity in context.portfolio.positions.items() if quantity > 0
        }
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(2 * self.ulcer_window, self.trend_window) + 8,
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
        minimum = max(2 * self.ulcer_window, self.trend_window) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            close = bars["close"]
            ulcer = self._ulcer_index(close, self.ulcer_window)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_ulcer = ulcer.iloc[-1]
            previous_ulcer = ulcer.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna([latest_ulcer, previous_ulcer, latest_trend]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_ulcer = float(latest_ulcer)
            previous_ulcer = float(previous_ulcer)
            latest_trend = float(latest_trend)
            if latest_close <= 0:
                continue
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    previous_ulcer > self.entry_threshold
                    and latest_ulcer <= self.entry_threshold
                    and latest_ulcer < previous_ulcer
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_ulcer >= self.exit_threshold
                    or latest_close < latest_trend
                ),
                "score": float(-latest_ulcer),
            }
        return result

    @staticmethod
    def _ulcer_index(close: pd.Series, window: int = 14) -> pd.Series:
        rolling_max = close.rolling(window, min_periods=window).max()
        drawdown_pct = 100 * (close - rolling_max) / (rolling_max.abs() + 1e-10)
        return drawdown_pct.pow(2).rolling(window, min_periods=window).mean().pow(0.5)
