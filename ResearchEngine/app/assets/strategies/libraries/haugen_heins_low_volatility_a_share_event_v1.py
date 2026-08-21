"""豪根—海因斯风格 A 股低波动异象研究策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class HaugenHeinsLowVolatilityAShareEventStrategy:
    """行业内低波动、低下行波动与浅回撤的月度现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "amount", "industry", "pe_ratio", "pb_ratio", "circulating_market_cap"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 25,
                 max_industry_holdings: int = 5, single_weight: float = 0.05,
                 min_amount: float = 20_000_000.0) -> None:
        self.universe, self.max_holdings = universe, max_holdings
        self.max_industry_holdings, self.single_weight, self.min_amount = max_industry_holdings, single_weight, min_amount

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"低波动异象策略缺少数据字段: {sorted(missing)}")
        context.schedule.monthly(lambda ctx: self.rebalance(ctx), trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        fields = ["close", "amount", "industry", "pe_ratio", "pb_ratio", "circulating_market_cap"]
        history = context.data.history(symbols, fields, 121)
        target = self._select(self._candidates(history, symbols), holdings)
        for symbol in holdings - set(target.index):
            context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * float(history["close"][s].dropna().iloc[-1]) for s in holdings if not history["close"][s].dropna().empty)
        target_value = total_value * min(self.single_weight, 0.95 / max(len(target), 1))
        for symbol in target.index:
            context.orders.target_value(symbol, target_value)

    def _candidates(self, history, symbols):
        rows = []
        for symbol in symbols:
            close = history["close"][symbol].dropna()
            values = {field: history[field][symbol].dropna() for field in ("amount", "industry", "pe_ratio", "pb_ratio", "circulating_market_cap")}
            if len(close) < 121 or any(series.empty for series in values.values()) or values["amount"].tail(20).mean() < self.min_amount:
                continue
            pe, pb, cap = (float(values[field].iloc[-1]) for field in ("pe_ratio", "pb_ratio", "circulating_market_cap"))
            if not 0 < pe <= 100 or not 0 < pb <= 15 or cap <= 0:
                continue
            returns = close.iloc[-121:].pct_change().dropna()
            downside = returns[returns < 0]
            if len(downside) < 20:
                continue
            vol, down_vol = returns.std() * np.sqrt(252.0), downside.std() * np.sqrt(252.0)
            drawdown = (close.iloc[-121:] / close.iloc[-121:].cummax() - 1.0).min()
            if not np.isfinite(vol) or not np.isfinite(down_vol) or vol <= 0 or down_vol <= 0:
                continue
            rows.append((symbol, values["industry"].iloc[-1], cap, vol, down_vol, drawdown))
        frame = pd.DataFrame(rows, columns=["symbol", "industry", "cap", "volatility", "downside_volatility", "max_drawdown"])
        if frame.empty:
            return frame
        frame = frame[frame.cap >= frame.cap.quantile(0.05)].copy()
        frame = frame[frame.groupby("industry").symbol.transform("count") >= 5].copy()
        frame["score"] = (0.50 * (1 - frame.groupby("industry").volatility.rank(pct=True))
                          + 0.30 * (1 - frame.groupby("industry").downside_volatility.rank(pct=True))
                          + 0.20 * frame.groupby("industry").max_drawdown.rank(pct=True))
        return frame.sort_values("score", ascending=False)

    def _select(self, candidates, holdings):
        if candidates.empty:
            return candidates.set_index("symbol")
        candidates = candidates.copy(); candidates["rank"] = range(1, len(candidates) + 1)
        retained = candidates[(candidates.symbol.isin(holdings)) & (candidates["rank"] <= 50)]
        ordered = pd.concat([retained, candidates[~candidates.symbol.isin(retained.symbol)]])
        selected, counts = [], {}
        for row in ordered.itertuples():
            if counts.get(row.industry, 0) >= self.max_industry_holdings:
                continue
            selected.append(row.symbol); counts[row.industry] = counts.get(row.industry, 0) + 1
            if len(selected) == self.max_holdings:
                break
        return candidates.set_index("symbol").loc[selected]
