"""约翰·聂夫低市盈率法 A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class NeffLowPeAShareEventStrategy:
    """低 PE、盈利增长、分红与总回报率/PE 综合筛选的月度策略。"""

    execution_mode = "event"
    required_fields = frozenset({
        "open", "high", "low", "close", "pe_ratio", "dividend_yield",
        "inc_net_profit_year_on_year",
    })

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 min_pe: float = 1.0, max_pe: float = 20.0,
                 min_growth: float = 7.0, min_dividend: float = 2.0,
                 min_ratio: float = 2.0) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.min_pe = min_pe
        self.max_pe = max_pe
        self.min_growth = min_growth
        self.min_dividend = min_dividend
        self.min_ratio = min_ratio

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"聂夫低市盈率策略缺少数据字段: {sorted(missing)}")
        def rebalance(ctx):
            self.rebalance(ctx)

        context.schedule.monthly(rebalance, trading_day=1)

    def rebalance(self, context) -> None:
        universe = self.universe or list(context.data.symbols)
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys(universe + list(holdings)))
        history = context.data.history(
            symbols,
            ["close", "pe_ratio", "dividend_yield", "inc_net_profit_year_on_year"],
            1,
        )
        latest = self._latest(history, symbols)
        if latest.empty:
            return
        latest = latest[
            (latest.pe_ratio > self.min_pe) & (latest.pe_ratio < self.max_pe)
            & (latest.inc_net_profit_year_on_year > self.min_growth)
            & (latest.dividend_yield > self.min_dividend)
        ].copy()
        latest["ratio"] = (
            latest.inc_net_profit_year_on_year + latest.dividend_yield
        ) / latest.pe_ratio
        target = latest[latest.ratio >= self.min_ratio].sort_values("ratio", ascending=False).head(self.max_holdings)
        target_symbols = set(target.index)
        for symbol in holdings - target_symbols:
            context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(s) * float(latest.loc[s, "close"])
            for s in holdings if s in latest.index and pd.notna(latest.loc[s, "close"])
        )
        for symbol in target_symbols - holdings:
            context.orders.target_value(symbol, total_value / max(self.max_holdings, 1))

    @staticmethod
    def _latest(history, symbols):
        rows = {}
        for symbol in symbols:
            values = {field: history[field][symbol].dropna().iloc[-1]
                      for field in history if symbol in history[field] and not history[field][symbol].dropna().empty}
            if len(values) == len(history):
                rows[symbol] = values
        return pd.DataFrame.from_dict(rows, orient="index")
