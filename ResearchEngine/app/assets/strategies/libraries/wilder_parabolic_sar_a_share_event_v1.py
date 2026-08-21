"""威尔斯·威尔德抛物线 SAR A 股趋势策略。"""

from __future__ import annotations

import pandas as pd


class WilderParabolicSarAShareEventStrategy:
    """每周按 SAR 多头安全边际选股，每日以 SAR 反转离场。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})
    required_market_state = frozenset({"suspended", "limit_up", "limit_down"})

    def __init__(self, universe: list[str] | None = None, max_holdings: int = 10,
                 pool_size: int = 15, lookback: int = 120,
                 af_step: float = 0.02, af_max: float = 0.20) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.pool_size = pool_size
        self.lookback = lookback
        self.af_step = af_step
        self.af_max = af_max

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"抛物线 SAR 策略缺少数据字段: {sorted(missing)}")

        def rebuild_pool(ctx):
            self.rebuild_pool(ctx)

        context.schedule.weekly(rebuild_pool, weekday=0)
        context.schedule.daily(self.rebalance)

    def rebuild_pool(self, context) -> None:
        symbols = self.universe or list(context.data.symbols)
        history = context.data.history(symbols, ["high", "low", "close"], self.lookback)
        scores = {}
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < self.lookback:
                continue
            sar, trend = self._sar(bars.high, bars.low, bars.close)
            if trend.iloc[-1] == 1 and pd.notna(sar.iloc[-1]):
                scores[symbol] = float(bars.close.iloc[-1] / sar.iloc[-1] - 1.0)
        context.state.sar_pool = [symbol for symbol, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:self.pool_size]]

    def rebalance(self, context) -> None:
        pool = getattr(context.state, "sar_pool", [])
        holdings = set(context.portfolio.positions)
        watch = list(dict.fromkeys(pool + list(holdings)))
        if not watch:
            return
        history = context.data.history(watch, ["high", "low", "close"], self.lookback)
        metrics = {}
        for symbol in watch:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) >= self.lookback:
                sar, trend = self._sar(bars.high, bars.low, bars.close)
                metrics[symbol] = (float(bars.close.iloc[-1]), float(sar.iloc[-1]), int(trend.iloc[-1]))
        for symbol in holdings:
            item = metrics.get(symbol)
            if item is None or item[2] < 0 or item[0] < item[1]:
                context.orders.close(symbol)
        survivors = {symbol for symbol in holdings if symbol in metrics and metrics[symbol][2] == 1 and metrics[symbol][0] >= metrics[symbol][1]}
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * metrics[s][0] for s in survivors)
        for symbol in pool:
            if symbol in survivors or len(survivors) >= self.max_holdings:
                continue
            context.orders.target_value(symbol, total_value / self.max_holdings)
            survivors.add(symbol)

    def _sar(self, high, low, close):
        sar = pd.Series(float("nan"), index=high.index)
        trend = pd.Series(0, index=high.index, dtype=int)
        if len(high) < 7:
            return sar, trend
        start = 5
        trend.iloc[start] = 1 if close.iloc[start] >= close.iloc[start - 1] else -1
        sar.iloc[start] = low.iloc[:start].min() if trend.iloc[start] == 1 else high.iloc[:start].max()
        ep, af = (high.iloc[start], self.af_step) if trend.iloc[start] == 1 else (low.iloc[start], self.af_step)
        for index in range(start + 1, len(high)):
            previous = sar.iloc[index - 1]
            if trend.iloc[index - 1] == 1:
                value = min(previous + af * (ep - previous), low.iloc[index - 1], low.iloc[index - 2])
                if low.iloc[index] < value:
                    trend.iloc[index], sar.iloc[index], ep, af = -1, ep, low.iloc[index], self.af_step
                else:
                    trend.iloc[index], sar.iloc[index] = 1, value
                    if high.iloc[index] > ep:
                        ep, af = high.iloc[index], min(af + self.af_step, self.af_max)
            else:
                value = max(previous + af * (ep - previous), high.iloc[index - 1], high.iloc[index - 2])
                if high.iloc[index] > value:
                    trend.iloc[index], sar.iloc[index], ep, af = 1, ep, high.iloc[index], self.af_step
                else:
                    trend.iloc[index], sar.iloc[index] = -1, value
                    if low.iloc[index] < ep:
                        ep, af = low.iloc[index], min(af + self.af_step, self.af_max)
        return sar, trend
