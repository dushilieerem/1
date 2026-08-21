"""凯特纳通道 A 股趋势突破策略。"""

from __future__ import annotations

import pandas as pd


class KeltnerChannelBreakoutAShareEventStrategy:
    """突破 EMA 加 ATR 上轨入场，跌破中轨或下轨退出的现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 single_weight: float = 0.09, ema_window: int = 20,
                 atr_window: int = 10, multiplier: float = 2.0) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.ema_window = ema_window
        self.atr_window = atr_window
        self.multiplier = multiplier

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"凯特纳通道策略缺少数据字段: {sorted(missing)}")
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
            if len(bars) < max(self.ema_window, self.atr_window) + 2:
                continue
            middle, upper, lower = self._channels(bars.high, bars.low, bars.close)
            previous_upper = upper.iloc[-2]
            if pd.isna([middle.iloc[-1], upper.iloc[-1], lower.iloc[-1], previous_upper]).any():
                continue
            close = bars.close.iloc[-1]
            result[symbol] = {
                "close": float(close),
                "entry": bool(bars.close.iloc[-2] <= previous_upper and close > upper.iloc[-1]),
                "exit": bool(close < middle.iloc[-1] or bars.low.iloc[-1] < lower.iloc[-1]),
                "score": float((close - upper.iloc[-1]) / max(middle.iloc[-1], 1e-8)),
            }
        return result

    def _channels(self, high, low, close):
        previous_close = close.shift()
        true_range = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
        atr = true_range.ewm(alpha=1 / self.atr_window, adjust=False, min_periods=self.atr_window).mean()
        middle = close.ewm(span=self.ema_window, adjust=False, min_periods=self.ema_window).mean()
        return middle, middle + self.multiplier * atr, middle - self.multiplier * atr
