"""股息增长 A 股研究策略。"""

from __future__ import annotations

import pandas as pd


class DividendGrowthAShareEventStrategy:
    """连续五年派息且最近一年不降的中等股息率月度策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "dividend_yield", "pe_ttm", "total_mv", "dividend_cash_per_share"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 min_years: int = 5, min_dividend_yield: float = 0.01,
                 max_dividend_yield: float = 0.05, min_market_cap: float = 3_000_000_000.0) -> None:
        self.universe, self.max_holdings, self.min_years = universe, max_holdings, min_years
        self.min_dividend_yield, self.max_dividend_yield, self.min_market_cap = min_dividend_yield, max_dividend_yield, min_market_cap

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"股息增长策略缺少数据字段: {sorted(missing)}")
        context.schedule.monthly(lambda ctx: self.rebalance(ctx), trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(symbols, list(self.required_fields - {"open", "high", "low"}), self.min_years * 366)
        target = self._candidates(history, symbols).sort_values("dividend_yield", ascending=False).head(self.max_holdings)
        for symbol in holdings - set(target.index):
            context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * float(history["close"][s].dropna().iloc[-1]) for s in holdings if not history["close"][s].dropna().empty)
        for symbol in target.index:
            context.orders.target_value(symbol, total_value / self.max_holdings)

    def _candidates(self, history, symbols):
        rows = []
        for symbol in symbols:
            latest = {field: history[field][symbol].dropna() for field in ("dividend_yield", "pe_ttm", "total_mv")}
            if any(values.empty for values in latest.values()):
                continue
            dividend_yield, pe, market_cap = (float(latest[field].iloc[-1]) for field in latest)
            if not self.min_dividend_yield <= dividend_yield <= self.max_dividend_yield or pe <= 0 or market_cap < self.min_market_cap:
                continue
            annual = history["dividend_cash_per_share"][symbol].fillna(0.0).groupby(history["dividend_cash_per_share"].index.year).sum()
            payments = annual.tail(self.min_years)
            if len(payments) < self.min_years or (payments <= 0).any() or payments.iloc[-1] < payments.iloc[-2]:
                continue
            rows.append((symbol, dividend_yield))
        return pd.DataFrame(rows, columns=["symbol", "dividend_yield"]).set_index("symbol")
