"""Kaufman Adaptive Moving Average A 股日频趋势策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class KaufmanAdaptiveMovingAverageAShareEventStrategy:
    """使用 KAMA 自适应均线和长期趋势过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        er_window: int = 10,
        fast_window: int = 2,
        slow_window: int = 30,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.er_window = er_window
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"KAMA 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.trend_window, self.er_window) + self.slow_window + 8,
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
        minimum = max(self.trend_window, self.er_window) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            close = bars["close"]
            kama = self._kama(
                close,
                self.er_window,
                self.fast_window,
                self.slow_window,
            )
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_kama = kama.iloc[-1]
            previous_kama = kama.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna([latest_kama, previous_kama, latest_trend]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_kama = float(latest_kama)
            previous_kama = float(previous_kama)
            latest_trend = float(latest_trend)
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    close.iloc[-2] <= previous_kama
                    and latest_close > latest_kama
                    and latest_kama > previous_kama
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_close < latest_kama
                    or latest_kama <= previous_kama
                    or latest_close < latest_trend
                ),
                "score": float((latest_close - latest_kama) / max(abs(latest_kama), 1e-8)),
            }
        return result

    @staticmethod
    def _kama(
        close: pd.Series,
        er_window: int = 10,
        fast_window: int = 2,
        slow_window: int = 30,
    ) -> pd.Series:
        change = close.diff(er_window).abs()
        volatility = close.diff().abs().rolling(
            er_window,
            min_periods=er_window,
        ).sum()
        efficiency_ratio = change / volatility
        efficiency_ratio = efficiency_ratio.where(volatility.notna())
        efficiency_ratio = efficiency_ratio.where(volatility.ne(0), 0.0)
        fast_constant = 2.0 / (fast_window + 1.0)
        slow_constant = 2.0 / (slow_window + 1.0)
        smoothing = (
            efficiency_ratio * (fast_constant - slow_constant) + slow_constant
        ) ** 2

        values = np.full(len(close), np.nan, dtype=float)
        for position in range(len(close)):
            if pd.isna(smoothing.iloc[position]) or pd.isna(close.iloc[position]):
                continue
            if position == 0 or pd.isna(values[position - 1]):
                values[position] = float(close.iloc[position])
            else:
                values[position] = values[position - 1] + smoothing.iloc[position] * (
                    close.iloc[position] - values[position - 1]
                )
        return pd.Series(values, index=close.index, name=close.name)
