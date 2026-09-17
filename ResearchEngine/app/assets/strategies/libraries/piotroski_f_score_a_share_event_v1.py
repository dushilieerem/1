"""Piotroski F-Score A 股会计质量研究策略。"""

from __future__ import annotations

import pandas as pd


class PiotroskiFScoreAShareEventStrategy:
    """在低 PB 股票中以九项点时财务指标筛选高会计质量标的。"""

    execution_mode = "event"
    required_fields = frozenset({
        "open", "high", "low", "close", "pb_mrq", "total_mv", "total_assets",
        "total_liabilities", "current_assets", "current_liabilities", "total_shares",
        "operating_revenue_ttm", "operating_cost_ttm", "net_profit_ttm",
        "net_cashflow_operating_ttm",
    })

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 pb_percentile: float = 0.30, min_fscore: int = 6,
                 min_market_cap: float = 3_000_000_000.0, comparison_days: int = 90) -> None:
        self.universe, self.max_holdings = universe, max_holdings
        self.pb_percentile, self.min_fscore = pb_percentile, min_fscore
        self.min_market_cap, self.comparison_days = min_market_cap, comparison_days

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Piotroski F-Score 策略缺少数据字段: {sorted(missing)}")
        context.schedule.monthly(lambda ctx: self.rebalance(ctx), trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        fields = list(self.required_fields - {"open", "high", "low"})
        history = context.data.history(symbols, fields, self.comparison_days + 1)
        candidates = self._candidates(history, symbols)
        target = candidates[(candidates.fscore >= self.min_fscore) & (candidates.pb_mrq <= candidates.pb_mrq.quantile(self.pb_percentile))]
        target = target.sort_values(["fscore", "pb_mrq"], ascending=[False, True]).head(self.max_holdings)
        for symbol in holdings - set(target.index):
            context.orders.close(symbol)
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(s) * float(history["close"][s].dropna().iloc[-1])
            for s in holdings if not history["close"][s].dropna().empty
        )
        for symbol in target.index:
            context.orders.target_value(symbol, total_value / self.max_holdings)

    def _candidates(self, history, symbols):
        rows = []
        for symbol in symbols:
            latest = {field: frame[symbol].dropna() for field, frame in history.items()}
            if any(len(values) < self.comparison_days + 1 for values in latest.values()):
                continue
            now = {field: float(values.iloc[-1]) for field, values in latest.items()}
            prev = {field: float(values.iloc[-self.comparison_days - 1]) for field, values in latest.items()}
            if now["pb_mrq"] <= 0 or now["total_mv"] < self.min_market_cap or min(now["total_assets"], now["current_liabilities"]) <= 0:
                continue
            fscore = self.fscore(now, prev)
            rows.append((symbol, now["pb_mrq"], fscore))
        return pd.DataFrame(rows, columns=["symbol", "pb_mrq", "fscore"]).set_index("symbol")

    @staticmethod
    def fscore(now, prev) -> int:
        roa, previous_roa = now["net_profit_ttm"] / now["total_assets"], prev["net_profit_ttm"] / prev["total_assets"]
        current_ratio, previous_ratio = now["current_assets"] / now["current_liabilities"], prev["current_assets"] / prev["current_liabilities"]
        leverage = now["total_liabilities"] / now["total_assets"]
        previous_leverage = prev["total_liabilities"] / prev["total_assets"]
        margin = (now["operating_revenue_ttm"] - now["operating_cost_ttm"]) / now["operating_revenue_ttm"]
        previous_margin = (prev["operating_revenue_ttm"] - prev["operating_cost_ttm"]) / prev["operating_revenue_ttm"]
        turnover, previous_turnover = now["operating_revenue_ttm"] / now["total_assets"], prev["operating_revenue_ttm"] / prev["total_assets"]
        return sum((
            roa > 0, now["net_cashflow_operating_ttm"] > 0, roa > previous_roa,
            now["net_cashflow_operating_ttm"] > now["net_profit_ttm"], leverage < previous_leverage,
            current_ratio > previous_ratio, now["total_shares"] <= prev["total_shares"],
            margin > previous_margin, turnover > previous_turnover,
        ))
