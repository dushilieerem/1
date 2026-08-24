"""法玛—弗伦奇小盘价值 A 股研究策略。"""

from __future__ import annotations

import pandas as pd


class FamaFrenchSmallValueAShareEventStrategy:
    """行业内低 PB、低 PE 和小流通市值的月度现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "amount", "industry", "pe_ratio", "pb_ratio", "circulating_market_cap"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 30,
                 max_industry_holdings: int = 6, single_weight: float = 0.05,
                 min_amount: float = 20_000_000.0) -> None:
        self.universe, self.max_holdings = universe, max_holdings
        self.max_industry_holdings, self.single_weight, self.min_amount = max_industry_holdings, single_weight, min_amount

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"法玛—弗伦奇策略缺少数据字段: {sorted(missing)}")
        def rebalance(ctx):
            self.rebalance(ctx)

        context.schedule.monthly(rebalance, trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        fields = ["close", "amount", "industry", "pe_ratio", "pb_ratio", "circulating_market_cap"]
        history = context.data.history(symbols, fields, 20)
        candidates = self._candidates(history, symbols)
        target = self._select(candidates, holdings)
        for symbol in holdings - set(target.index):
            context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * float(history["close"][s].dropna().iloc[-1]) for s in holdings if not history["close"][s].dropna().empty)
        value = total_value * min(self.single_weight, 0.95 / max(len(target), 1))
        for symbol in target.index:
            context.orders.target_value(symbol, value)

    def _candidates(self, history, symbols):
        rows = []
        for symbol in symbols:
            latest = {field: history[field][symbol].dropna() for field in history}
            if any(series.empty for series in latest.values()) or latest["amount"].tail(20).mean() < self.min_amount:
                continue
            pe, pb, cap = (float(latest[field].iloc[-1]) for field in ("pe_ratio", "pb_ratio", "circulating_market_cap"))
            if pe <= 0 or pb <= 0 or cap <= 0:
                continue
            rows.append((symbol, latest["industry"].iloc[-1], pe, pb, cap))
        frame = pd.DataFrame(rows, columns=["symbol", "industry", "pe", "pb", "cap"])
        if frame.empty:
            return frame
        frame = frame[frame.cap >= frame.cap.quantile(0.05)].copy()
        counts = frame.groupby("industry").symbol.transform("count")
        frame = frame[counts >= 5].copy()
        frame["score"] = (0.50 * frame.groupby("industry").pb.rank(pct=True, ascending=False)
                          + 0.25 * frame.groupby("industry").pe.rank(pct=True, ascending=False)
                          + 0.25 * frame.groupby("industry").cap.rank(pct=True, ascending=False))
        return frame.sort_values("score", ascending=False)

    def _select(self, candidates, holdings):
        if candidates.empty:
            return candidates
        candidates = candidates.copy()
        candidates["rank"] = range(1, len(candidates) + 1)
        retained = candidates[(candidates.symbol.isin(holdings)) & (candidates["rank"] <= 60)]
        ordered = pd.concat([retained, candidates[~candidates.symbol.isin(retained.symbol)]])
        selected, counts = [], {}
        for row in ordered.itertuples():
            if counts.get(row.industry, 0) >= self.max_industry_holdings:
                continue
            selected.append(row.symbol); counts[row.industry] = counts.get(row.industry, 0) + 1
            if len(selected) == self.max_holdings:
                break
        return candidates.set_index("symbol").loc[selected]
