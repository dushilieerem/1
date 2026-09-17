"""德邦特—塞勒风格 A 股长期反转研究策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class DeBondtThalerLongTermReversalAShareEventStrategy:
    """行业内长期输家、近期恢复与低 PB 的月度现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "amount", "the_sw_industry_code", "pe_ttm", "pb_mrq", "current_mv"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 20,
                 max_industry_holdings: int = 4, single_weight: float = 0.05,
                 min_amount: float = 20_000_000.0) -> None:
        self.universe, self.max_holdings = universe, max_holdings
        self.max_industry_holdings, self.single_weight, self.min_amount = max_industry_holdings, single_weight, min_amount

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"长期反转策略缺少数据字段: {sorted(missing)}")
        context.schedule.monthly(lambda ctx: self.rebalance(ctx), trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        fields = ["close", "amount", "the_sw_industry_code", "pe_ttm", "pb_mrq", "current_mv"]
        history = context.data.history(symbols, fields, 757)
        target = self._select(self._candidates(history, symbols), holdings)
        for symbol in holdings - set(target.index):
            context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(s) * float(history["close"][s].dropna().iloc[-1])
            for s in holdings if not history["close"][s].dropna().empty
        )
        target_value = total_value * min(self.single_weight, 0.95 / max(len(target), 1))
        for symbol in target.index:
            context.orders.target_value(symbol, target_value)

    def _candidates(self, history, symbols):
        rows = []
        for symbol in symbols:
            close = history["close"][symbol].dropna()
            amount = history["amount"][symbol].reindex(close.index).fillna(0.0)
            values = {field: history[field][symbol].dropna() for field in ("the_sw_industry_code", "pe_ttm", "pb_mrq", "current_mv")}
            if len(close) < 757 or any(series.empty for series in values.values()) or amount.tail(20).mean() < self.min_amount:
                continue
            pe, pb, cap = (float(values[field].iloc[-1]) for field in ("pe_ttm", "pb_mrq", "current_mv"))
            if not 0 < pe <= 80 or not 0 < pb <= 10 or cap <= 0:
                continue
            long_return = close.iloc[-22] / close.iloc[-757] - 1.0
            recovery = close.iloc[-1] / close.iloc[-64] - 1.0
            volatility = close.iloc[-121:].pct_change().std() * np.sqrt(252.0)
            if not np.isfinite(long_return) or not np.isfinite(volatility) or long_return <= -0.95 or long_return >= 8 or recovery <= 0:
                continue
            rows.append((symbol, values["the_sw_industry_code"].iloc[-1], pb, cap, long_return, recovery, volatility))
        frame = pd.DataFrame(rows, columns=["symbol", "industry", "pb", "cap", "long_return", "recovery", "volatility"])
        if frame.empty:
            return frame
        frame = frame[frame.cap >= frame.cap.quantile(0.05)]
        frame = frame[frame.volatility <= frame.volatility.quantile(0.90)].copy()
        frame = frame[frame.groupby("industry").symbol.transform("count") >= 5].copy()
        frame["reversal_score"] = 1 - frame.groupby("industry").long_return.rank(pct=True)
        frame = frame[frame.reversal_score >= 0.70].copy()
        frame["score"] = (0.70 * frame.reversal_score + 0.20 * frame.groupby("industry").recovery.rank(pct=True)
                          + 0.10 * (1 - frame.groupby("industry").pb.rank(pct=True)))
        return frame.sort_values("score", ascending=False)

    def _select(self, candidates, holdings):
        if candidates.empty:
            return candidates.set_index("symbol")
        candidates = candidates.copy()
        candidates["rank"] = range(1, len(candidates) + 1)
        retained = candidates[(candidates.symbol.isin(holdings)) & (candidates["rank"] <= 40)]
        ordered = pd.concat([retained, candidates[~candidates.symbol.isin(retained.symbol)]])
        selected, counts = [], {}
        for row in ordered.itertuples():
            if counts.get(row.industry, 0) >= self.max_industry_holdings:
                continue
            selected.append(row.symbol); counts[row.industry] = counts.get(row.industry, 0) + 1
            if len(selected) == self.max_holdings:
                break
        return candidates.set_index("symbol").loc[selected]
