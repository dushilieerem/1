"""欧奈尔 CANSLIM 的无基本面数据研究版。"""

from __future__ import annotations

import pandas as pd


class OneilCanslimLiteAShareEventStrategy:
    """仅保留价格强度、简化基底突破和市场趋势控制的年度调仓策略。

    这不是完整 CANSLIM：不含 C/A/I/S 因子，也不筛除 ST、停牌、退市或次新股。
    """

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})
    execution_assumptions = frozenset({"daily_open", "no_slippage"})

    def __init__(
        self,
        benchmark_symbol: str = "000300.SH",
        universe: list[str] | None = None,
        max_holdings: int = 20,
        momentum_window: int = 250,
        trend_window: int = 250,
    ) -> None:
        self.benchmark_symbol = benchmark_symbol
        self.universe = universe
        self.max_holdings = max_holdings
        self.momentum_window = momentum_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"CANSLIM Lite 策略缺少数据字段: {sorted(missing)}")
        context.state.last_rebalance_year = None

        def rebalance(ctx):
            self.rebalance(ctx)

        context.schedule.monthly(rebalance, trading_day=1)

    def rebalance(self, context) -> None:
        if context.state.last_rebalance_year == context.current_dt.year:
            return
        universe = self.universe or [symbol for symbol in context.data.symbols if symbol != self.benchmark_symbol]
        close = context.data.history(universe, ["close"], self.momentum_window + 1)["close"]
        benchmark = context.data.history([self.benchmark_symbol], ["close"], self.trend_window)["close"]
        if len(close) < self.momentum_window + 1 or len(benchmark) < self.trend_window:
            return
        benchmark_close = benchmark[self.benchmark_symbol].dropna()
        if len(benchmark_close) < self.trend_window:
            return

        context.state.last_rebalance_year = context.current_dt.year
        holdings = [symbol for symbol in context.portfolio.positions if context.portfolio.quantity(symbol) > 0]
        for symbol in holdings:
            context.orders.close(symbol)

        momentum = close.iloc[-1] / close.iloc[0] - 1
        threshold = momentum.quantile(0.60)
        candidates = [
            symbol for symbol in universe
            if pd.notna(momentum.get(symbol))
            and momentum[symbol] >= threshold
            and self._base_breakout(close[symbol].dropna())
        ]
        candidates = sorted(candidates, key=lambda symbol: momentum[symbol], reverse=True)[:self.max_holdings]
        if not candidates:
            return

        exposure = 1.0 if benchmark_close.iloc[-1] > benchmark_close.iloc[-self.trend_window:].mean() else 0.5
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(symbol) * float(close[symbol].dropna().iloc[-1])
            for symbol in holdings if symbol in close
        )
        target_value = total_value * exposure * 0.99 / len(candidates)
        for symbol in candidates:
            context.orders.target_value(symbol, target_value)

    @staticmethod
    def _base_breakout(close: pd.Series) -> bool:
        """以月末收盘价近似原示例的 3–10 月基底突破条件。"""
        monthly = close.resample("ME").last().dropna()
        if len(monthly) < 3:
            return False
        latest = monthly.iloc[-1]
        for months in range(3, min(10, len(monthly)) + 1):
            base = monthly.iloc[-months]
            middle = monthly.iloc[-months + 1:-1]
            if latest > base and (middle < base).all():
                return True
        return False
