"""亚历山大·埃尔德三重滤网 A 股研究策略。"""

from __future__ import annotations

import pandas as pd


class ElderTripleScreenAShareEventStrategy:
    """周趋势、日线 KDJ 回调金叉和可交易状态由引擎共同过滤。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 single_weight: float = 0.10, kdj_window: int = 9) -> None:
        self.universe, self.max_holdings, self.single_weight, self.kdj_window = universe, max_holdings, single_weight, kdj_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"三重滤网策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(symbols, ["open", "high", "low", "close"], 75)
        metrics = self._metrics(history, symbols)
        for symbol in holdings:
            if symbol not in metrics or metrics[symbol]["exit"]:
                context.orders.close(symbol)
        survivors = {s for s in holdings if s in metrics and not metrics[s]["exit"]}
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * metrics[s]["close"] for s in survivors)
        candidates = sorted(((s, item["score"]) for s, item in metrics.items() if s not in holdings and item["entry"]), key=lambda item: item[1], reverse=True)
        for symbol, _ in candidates[:max(0, self.max_holdings - len(survivors))]:
            context.orders.target_value(symbol, total_value * self.single_weight)

    def _metrics(self, history, symbols):
        result = {}
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < 50:
                continue
            close, high, low = bars.close, bars.high, bars.low
            weekly = close.resample("W-FRI").last().dropna()
            if len(weekly) < 10:
                continue
            k, d = self._kdj(high, low, close)
            golden = k.iloc[-2] <= d.iloc[-2] and k.iloc[-1] > d.iloc[-1]
            trend = weekly.iloc[-5:].mean() > weekly.iloc[-10:].mean()
            entry = trend and k.iloc[-1] < 30 and golden
            result[symbol] = {"close": float(close.iloc[-1]), "entry": bool(entry), "exit": bool(close.iloc[-1] < weekly.iloc[-10:].mean()), "score": float(30 - k.iloc[-1])}
        return result

    def _kdj(self, high, low, close):
        lowest, highest = low.rolling(self.kdj_window).min(), high.rolling(self.kdj_window).max()
        rsv = 100 * (close - lowest) / (highest - lowest).replace(0, float("nan"))
        return rsv.ewm(alpha=1 / 3, adjust=False).mean(), rsv.ewm(alpha=1 / 3, adjust=False).mean().ewm(alpha=1 / 3, adjust=False).mean()
