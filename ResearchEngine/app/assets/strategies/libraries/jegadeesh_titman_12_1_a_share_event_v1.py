"""杰格迪什—蒂特曼 12-1 中期动量 A 股研究策略。"""

from __future__ import annotations

import pandas as pd


class JegadeeshTitman121AShareEventStrategy:
    """按行业相对动量和低波动评分的月度现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "amount", "the_sw_industry_code"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 20,
                 max_industry_holdings: int = 4, single_weight: float = 0.05,
                 min_amount: float = 20_000_000.0) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.max_industry_holdings = max_industry_holdings
        self.single_weight = single_weight
        self.min_amount = min_amount

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"12-1 动量策略缺少数据字段: {sorted(missing)}")
        def rebalance(ctx):
            self.rebalance(ctx)

        context.schedule.monthly(rebalance, trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or list(context.data.symbols)
        symbols = list(dict.fromkeys(universe + list(holdings)))
        history = context.data.history(symbols, ["close", "amount", "the_sw_industry_code"], 253)
        candidates = self._candidates(history, symbols)
        target = self._select(candidates, holdings)
        for symbol in holdings - set(target.index):
            context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(symbol) * float(history["close"][symbol].dropna().iloc[-1])
            for symbol in holdings if not history["close"][symbol].dropna().empty
        )
        target_value = total_value * min(self.single_weight, 0.95 / max(len(target), 1))
        for symbol in target.index:
            context.orders.target_value(symbol, target_value)

    def _candidates(self, history, symbols):
        rows = []
        for symbol in symbols:
            close = history["close"][symbol].dropna()
            amount = history["amount"][symbol].reindex(close.index).fillna(0.0)
            industry = history["the_sw_industry_code"][symbol].dropna()
            if len(close) < 253 or len(industry) == 0 or amount.tail(20).mean() < self.min_amount:
                continue
            momentum_12_1 = close.iloc[-22] / close.iloc[-253] - 1.0
            momentum_6_1 = close.iloc[-22] / close.iloc[-127] - 1.0
            if momentum_12_1 <= 0:
                continue
            rows.append((symbol, industry.iloc[-1], momentum_12_1, momentum_6_1, close.pct_change().tail(60).std()))
        frame = pd.DataFrame(rows, columns=["symbol", "industry", "m12", "m6", "vol"]).dropna()
        if frame.empty:
            return frame
        frame = frame[frame["vol"] <= frame["vol"].quantile(0.9)].copy()
        counts = frame.groupby("industry")["symbol"].transform("count")
        frame = frame[counts >= 5].copy()
        frame["score"] = (0.60 * frame.groupby("industry")["m12"].rank(pct=True)
                          + 0.25 * frame.groupby("industry")["m6"].rank(pct=True)
                          + 0.15 * (1 - frame.groupby("industry")["vol"].rank(pct=True)))
        return frame.sort_values("score", ascending=False)

    def _select(self, candidates, holdings):
        if candidates.empty:
            return candidates
        candidates = candidates.copy()
        candidates["rank"] = range(1, len(candidates) + 1)
        retained = candidates[(candidates.symbol.isin(holdings)) & (candidates["rank"] <= 50)]
        ordered = pd.concat([retained, candidates[~candidates.symbol.isin(retained.symbol)]])
        selected, industry_count = [], {}
        for row in ordered.itertuples():
            if industry_count.get(row.industry, 0) >= self.max_industry_holdings:
                continue
            selected.append(row.symbol)
            industry_count[row.industry] = industry_count.get(row.industry, 0) + 1
            if len(selected) == self.max_holdings:
                break
        return candidates.set_index("symbol").loc[selected]
