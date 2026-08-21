"""拉里·威廉斯 %R A 股趋势内超卖反转策略。"""

from __future__ import annotations

import pandas as pd


class WilliamsPercentRAShareEventStrategy:
    """上升趋势中 %R 从超卖区向上穿越时买入的现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 single_weight: float = 0.09, window: int = 14, oversold: float = -80.0,
                 overbought: float = -20.0) -> None:
        self.universe, self.max_holdings, self.single_weight = universe, max_holdings, single_weight
        self.window, self.oversold, self.overbought = window, oversold, overbought

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Williams %R 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(symbols, ["high", "low", "close"], 80)
        metrics = self._metrics(history, symbols)
        survivors = set()
        for symbol in holdings:
            item = metrics.get(symbol)
            if item is None or item["exit"]:
                context.orders.close(symbol)
            else:
                survivors.add(symbol)
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * metrics[s]["close"] for s in survivors)
        candidates = sorted(((s, item["score"]) for s, item in metrics.items() if s not in holdings and item["entry"]), key=lambda item: item[1], reverse=True)
        for symbol, _ in candidates[:max(0, self.max_holdings - len(survivors))]:
            context.orders.target_value(symbol, total_value * self.single_weight)

    def _metrics(self, history, symbols):
        result = {}
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < 61:
                continue
            percent_r = self._percent_r(bars.high, bars.low, bars.close)
            if pd.isna(percent_r.iloc[-2]) or pd.isna(percent_r.iloc[-1]):
                continue
            close, trend = bars.close.iloc[-1], bars.close.iloc[-60:].mean()
            cross = percent_r.iloc[-2] <= self.oversold and percent_r.iloc[-1] > self.oversold
            result[symbol] = {
                "close": float(close),
                "entry": bool(close > trend and cross),
                "exit": bool(percent_r.iloc[-1] >= self.overbought or close < trend),
                "score": float(percent_r.iloc[-1] - self.oversold),
            }
        return result

    def _percent_r(self, high, low, close):
        highest, lowest = high.rolling(self.window).max(), low.rolling(self.window).min()
        return -100 * (highest - close) / (highest - lowest).replace(0, float("nan"))
