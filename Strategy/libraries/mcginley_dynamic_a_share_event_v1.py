"""McGinley Dynamic A 股日频趋势策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class McGinleyDynamicAShareEventStrategy:
    """使用 McGinley Dynamic 自适应均线和长期趋势过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        window: int = 14,
        k: float = 0.6,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.window = window
        self.k = k
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"McGinley Dynamic 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.window, self.trend_window) + 8,
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
        minimum = max(self.window, self.trend_window) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            close = bars["close"]
            dynamic = self._mcginley_dynamic(close, self.window, self.k)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_dynamic = dynamic.iloc[-1]
            previous_dynamic = dynamic.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna([latest_dynamic, previous_dynamic, latest_trend]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_dynamic = float(latest_dynamic)
            previous_dynamic = float(previous_dynamic)
            latest_trend = float(latest_trend)
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    close.iloc[-2] <= previous_dynamic
                    and latest_close > latest_dynamic
                    and latest_dynamic > previous_dynamic
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_close < latest_dynamic
                    or latest_dynamic <= previous_dynamic
                    or latest_close < latest_trend
                ),
                "score": float(
                    (latest_close - latest_dynamic) / max(abs(latest_dynamic), 1e-8)
                ),
            }
        return result

    @staticmethod
    def _mcginley_dynamic(
        close: pd.Series,
        window: int = 14,
        k: float = 0.6,
    ) -> pd.Series:
        values = np.full(len(close), np.nan, dtype=float)
        denominator_base = max(float(k) * window, 1e-8)
        for position in range(len(close)):
            price = close.iloc[position]
            if pd.isna(price):
                continue
            if position == 0 or pd.isna(values[position - 1]):
                values[position] = float(price)
                continue
            previous = values[position - 1]
            ratio = max(float(price) / max(abs(previous), 1e-8), 1e-8)
            denominator = denominator_base * ratio**4
            values[position] = previous + (float(price) - previous) / denominator
        return pd.Series(values, index=close.index, name=close.name)
