"""BBI 多空指数 A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class BbiTrendAShareEventStrategy:
    """使用 BBI 均线趋势和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        bbi_windows: tuple[int, int, int, int] = (3, 6, 12, 24),
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.bbi_windows = bbi_windows
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"BBI 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.trend_window, max(self.bbi_windows)) + 8,
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
        minimum = max(self.trend_window, max(self.bbi_windows)) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            close = bars["close"]
            bbi = self._bbi(close, self.bbi_windows)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_bbi = bbi.iloc[-1]
            previous_bbi = bbi.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna([latest_bbi, previous_bbi, latest_trend]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_bbi = float(latest_bbi)
            previous_bbi = float(previous_bbi)
            latest_trend = float(latest_trend)
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    close.iloc[-2] <= previous_bbi
                    and latest_close > latest_bbi
                    and latest_bbi > previous_bbi
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_close < latest_bbi
                    or latest_bbi <= previous_bbi
                    or latest_close < latest_trend
                ),
                "score": float((latest_close - latest_bbi) / max(abs(latest_bbi), 1e-8)),
            }
        return result

    @staticmethod
    def _bbi(
        close: pd.Series,
        windows: tuple[int, int, int, int] = (3, 6, 12, 24),
    ) -> pd.Series:
        return sum(
            close.rolling(window, min_periods=window).mean()
            for window in windows
        ) / len(windows)
