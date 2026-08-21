"""Fama-French/Carhart 多因子 A 股研究策略。"""

from __future__ import annotations

import pandas as pd


class FamaFrenchCarhartMultiFactorAShareEventStrategy:
    """小市值、低 PB 与 12-1 动量等权合成的月度现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "market_cap", "pb_ratio"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 min_market_cap: float = 3_000_000_000.0, size_weight: float = 0.34,
                 value_weight: float = 0.33, momentum_weight: float = 0.33) -> None:
        self.universe, self.max_holdings, self.min_market_cap = universe, max_holdings, min_market_cap
        self.size_weight, self.value_weight, self.momentum_weight = size_weight, value_weight, momentum_weight

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Fama-French 多因子策略缺少数据字段: {sorted(missing)}")

        def rebalance(ctx):
            self.rebalance(ctx)

        context.schedule.monthly(rebalance, trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(symbols, ["close", "market_cap", "pb_ratio"], 260)
        candidates = self._candidates(history, symbols)
        target = candidates.head(self.max_holdings)
        for symbol in holdings - set(target.index):
            context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * float(history["close"][s].dropna().iloc[-1]) for s in holdings if not history["close"][s].dropna().empty)
        for symbol in target.index:
            context.orders.target_value(symbol, total_value / self.max_holdings)

    def _candidates(self, history, symbols):
        rows = []
        for symbol in symbols:
            close = history["close"][symbol].dropna()
            cap, pb = history["market_cap"][symbol].dropna(), history["pb_ratio"][symbol].dropna()
            if len(close) < 260 or cap.empty or pb.empty or cap.iloc[-1] < self.min_market_cap or pb.iloc[-1] <= 0:
                continue
            rows.append((symbol, float(cap.iloc[-1]), float(pb.iloc[-1]), float(close.iloc[-22] / close.iloc[-260] - 1)))
        frame = pd.DataFrame(rows, columns=["symbol", "market_cap", "pb_ratio", "momentum"])
        if frame.empty:
            return frame.set_index("symbol")
        frame["score"] = (self.size_weight * (1 - frame.market_cap.rank(pct=True))
                          + self.value_weight * (1 - frame.pb_ratio.rank(pct=True))
                          + self.momentum_weight * frame.momentum.rank(pct=True))
        return frame.sort_values("score", ascending=False).set_index("symbol")
