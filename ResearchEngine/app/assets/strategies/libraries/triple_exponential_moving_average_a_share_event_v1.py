"""TEMA 三重指数移动平均线 A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class TripleExponentialMovingAverageAShareEventStrategy:
    """使用 TEMA 低滞后趋势和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        tema_window: int = 20,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.tema_window = tema_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"TEMA 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = {
            symbol for symbol, quantity in context.portfolio.positions.items() if quantity > 0
        }
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(3 * self.tema_window, self.trend_window) + 8,
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
        minimum = max(3 * self.tema_window, self.trend_window) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            close = bars["close"]
            tema = self._tema(close, self.tema_window)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_tema = tema.iloc[-1]
            previous_tema = tema.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna([latest_tema, previous_tema, latest_trend]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_tema = float(latest_tema)
            previous_tema = float(previous_tema)
            latest_trend = float(latest_trend)
            if latest_close <= 0:
                continue
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    close.iloc[-2] <= previous_tema
                    and latest_close > latest_tema
                    and latest_tema > previous_tema
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_close < latest_tema
                    or latest_tema <= previous_tema
                    or latest_close < latest_trend
                ),
                "score": float((latest_close - latest_tema) / max(abs(latest_tema), 1e-8)),
            }
        return result

    @staticmethod
    def _tema(close: pd.Series, window: int = 20) -> pd.Series:
        ema1 = close.ewm(span=window, adjust=False, min_periods=window).mean()
        ema2 = ema1.ewm(span=window, adjust=False, min_periods=window).mean()
        ema3 = ema2.ewm(span=window, adjust=False, min_periods=window).mean()
        return 3 * ema1 - 3 * ema2 + ema3
