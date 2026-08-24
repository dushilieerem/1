"""Heikin-Ashi A 股日频趋势策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class HeikinAshiTrendAShareEventStrategy:
    """使用 Heikin-Ashi 多头蜡烛和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

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
            raise ValueError(f"Heikin-Ashi 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["open", "high", "low", "close"],
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
        minimum = self.trend_window + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            candles = self._heikin_ashi(
                bars["open"],
                bars["high"],
                bars["low"],
                bars["close"],
            )
            trend = bars["close"].rolling(
                self.trend_window,
                min_periods=self.trend_window,
            ).mean()
            latest = candles.iloc[-1]
            previous = candles.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna(latest).any() or pd.isna(previous).any() or pd.isna(latest_trend):
                continue
            latest_close = float(bars["close"].iloc[-1])
            bullish = bool(latest["close"] > latest["open"])
            previous_bullish = bool(previous["close"] > previous["open"])
            result[symbol] = {
                "close": latest_close,
                "entry": bool(bullish and not previous_bullish and latest_close > latest_trend),
                "exit": bool(not bullish or latest_close < float(latest_trend)),
                "score": float(
                    (latest["close"] - latest["open"]) / max(abs(latest_close), 1e-8)
                ),
            }
        return result

    @staticmethod
    def _heikin_ashi(
        open_: pd.Series,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
    ) -> pd.DataFrame:
        ha_close = (open_ + high + low + close) / 4.0
        ha_open = pd.Series(np.nan, index=close.index, dtype=float)
        if len(close) > 0:
            ha_open.iloc[0] = (open_.iloc[0] + close.iloc[0]) / 2.0
            for position in range(1, len(close)):
                ha_open.iloc[position] = (
                    ha_open.iloc[position - 1] + ha_close.iloc[position - 1]
                ) / 2.0
        ha_high = pd.concat([high, ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([low, ha_open, ha_close], axis=1).min(axis=1)
        return pd.DataFrame(
            {"open": ha_open, "high": ha_high, "low": ha_low, "close": ha_close},
            index=close.index,
        )
