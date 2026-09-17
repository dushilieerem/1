"""戴维斯双击 A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class DavisDoublePlayAShareEventStrategy:
    """低 PE 历史分位、高盈利增长与高 ROE 的月度等权策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "pe_ttm", "roe", "inc_net_profit_year_on_year"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 min_growth: float = 10.0, min_roe: float = 10.0,
                 buy_pe_pct: float = 0.4, sell_pe_pct: float = 0.8,
                 hist_years: int = 3) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.min_growth = min_growth
        self.min_roe = min_roe
        self.buy_pe_pct = buy_pe_pct
        self.sell_pe_pct = sell_pe_pct
        self.hist_years = hist_years

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"戴维斯双击策略缺少数据字段: {sorted(missing)}")
        def rebalance(ctx):
            self.rebalance(ctx)

        context.schedule.monthly(rebalance, trading_day=1)

    def rebalance(self, context) -> None:
        universe = self.universe or list(context.data.symbols)
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys(universe + list(holdings)))
        count = max(self.hist_years * 366, 8)
        history = context.data.history(symbols, ["close", "pe_ttm", "roe", "inc_net_profit_year_on_year"], count)
        current = self._latest(history, symbols)
        if current.empty:
            return
        current = current[(current.pe_ttm > 0) & (current.roe > self.min_roe)
                          & (current.inc_net_profit_year_on_year > self.min_growth)].copy()
        current["pe_pct"] = [self._percentile(symbol, float(row.pe_ttm), history["pe_ttm"])
                              for symbol, row in current.iterrows()]
        target = current[current.pe_pct <= self.buy_pe_pct].sort_values("pe_pct").head(self.max_holdings)
        target_symbols = set(target.index)
        for symbol in holdings:
            row = current.loc[symbol] if symbol in current.index else None
            if row is None or float(row.pe_pct) > self.sell_pe_pct or symbol not in target_symbols:
                context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(s) * float(current.loc[s, "close"])
            for s in holdings if s in current.index and pd.notna(current.loc[s, "close"])
        )
        for symbol in target_symbols - holdings:
            context.orders.target_value(symbol, total_value / max(self.max_holdings, 1))

    @staticmethod
    def _latest(history, symbols):
        rows = {}
        for symbol in symbols:
            values = {}
            for field, frame in history.items():
                series = frame[symbol].dropna() if symbol in frame else pd.Series(dtype=float)
                if not series.empty:
                    values[field] = series.iloc[-1]
            if len(values) == len(history):
                rows[symbol] = values
        return pd.DataFrame.from_dict(rows, orient="index")

    @staticmethod
    def _percentile(symbol, current, frame):
        series = frame[symbol].dropna() if symbol in frame else pd.Series(dtype=float)
        series = series[series > 0]
        if len(series) < 8:
            return 0.5
        return float((series < current).sum() / len(series))
