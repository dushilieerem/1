"""Hull Moving Average A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class HullMovingAverageAShareEventStrategy:
    """使用低滞后的 HMA 交叉和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        hma_window: int = 20,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.hma_window = hma_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Hull Moving Average 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.trend_window, self.hma_window * 2) + int(self.hma_window**0.5) + 5,
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
        minimum = max(self.trend_window, self.hma_window * 2) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            close = bars["close"]
            hma = self._hull_moving_average(close, self.hma_window)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_hma = hma.iloc[-1]
            previous_hma = hma.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna([latest_hma, previous_hma, latest_trend]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_hma = float(latest_hma)
            latest_trend = float(latest_trend)
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    close.iloc[-2] <= previous_hma
                    and latest_close > latest_hma
                    and latest_hma > previous_hma
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_close < latest_hma
                    or latest_hma < previous_hma
                    or latest_close < latest_trend
                ),
                "score": float((latest_close - latest_hma) / max(abs(latest_hma), 1e-8)),
            }
        return result

    @staticmethod
    def _wma(close: pd.Series, window: int) -> pd.Series:
        weights = pd.Series(range(1, window + 1), dtype=float).to_numpy()
        denominator = float(weights.sum())
        return close.rolling(window, min_periods=window).apply(
            lambda values: float((values * weights).sum() / denominator),
            raw=True,
        )

    @classmethod
    def _hull_moving_average(cls, close: pd.Series, window: int = 20) -> pd.Series:
        half_window = max(window // 2, 1)
        smoothing_window = max(int(window**0.5), 1)
        raw = 2 * cls._wma(close, half_window) - cls._wma(close, window)
        return cls._wma(raw, smoothing_window)
