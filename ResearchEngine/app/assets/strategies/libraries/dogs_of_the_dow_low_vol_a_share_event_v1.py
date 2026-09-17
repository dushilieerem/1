"""奥希金斯狗股理论红利低波 A 股变体。"""

from __future__ import annotations

import pandas as pd


class DogsOfTheDowLowVolAShareEventStrategy:
    """年度按高股息前 30% 内低波动筛选的现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "pe_ttm", "dividend_yield_ttm"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 dividend_top: float = 0.30, vol_days: int = 250) -> None:
        self.universe, self.max_holdings, self.dividend_top, self.vol_days = universe, max_holdings, dividend_top, vol_days

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"狗股理论策略缺少数据字段: {sorted(missing)}")
        def rebalance_in_january(ctx):
            self._rebalance_in_january(ctx)

        context.schedule.monthly(rebalance_in_january, trading_day=1)

    def _rebalance_in_january(self, context) -> None:
        if context.current_dt.month == 1:
            self.rebalance(context)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(symbols, ["close", "pe_ttm", "dividend_yield_ttm"], self.vol_days)
        rows = []
        for symbol in symbols:
            close = history["close"][symbol].dropna()
            pe, dividend = history["pe_ttm"][symbol].dropna(), history["dividend_yield_ttm"][symbol].dropna()
            if len(close) < self.vol_days or pe.empty or dividend.empty or pe.iloc[-1] <= 0 or dividend.iloc[-1] <= 0:
                continue
            rows.append((symbol, float(dividend.iloc[-1]), float(close.pct_change().std())))
        candidates = pd.DataFrame(rows, columns=["symbol", "dividend", "vol"])
        if candidates.empty:
            return
        count = max(int(len(candidates) * self.dividend_top), self.max_holdings)
        target = candidates.sort_values("dividend", ascending=False).head(count).sort_values("vol").head(self.max_holdings).set_index("symbol")
        for symbol in holdings - set(target.index):
            context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * float(history["close"][s].dropna().iloc[-1]) for s in holdings if not history["close"][s].dropna().empty)
        for symbol in target.index:
            context.orders.target_value(symbol, total_value / self.max_holdings)
