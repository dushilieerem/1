"""唐奇安风格均线多头排列 A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class DonchianBullishMaAlignmentAShareEventStrategy:
    """单标的现金多头策略；信号基于前一收盘，订单于下一开盘成交。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "close"})
    required_market_state = frozenset({"up_and_down_status"})
    fixed_symbols = ("000858.SZ",)

    def __init__(
        self,
        symbol: str = "000858.SZ",
        stop_loss: float = 0.08,
        take_profit: float = 0.30,
        pullback_limit: float = 1.03,
    ) -> None:
        self.symbol = symbol
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.pullback_limit = pullback_limit

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"均线多头排列策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        history = context.data.history([self.symbol], ["close"], 61)["close"]
        if self.symbol not in history or len(history) < 61:
            return
        signal = self._signal(history[self.symbol].dropna())
        if signal is None:
            return

        quantity = context.portfolio.quantity(self.symbol)
        if quantity > 0 and self._should_exit(signal, context.portfolio.average_cost(self.symbol)):
            context.orders.close(self.symbol)
            return
        if quantity == 0 and signal["entry"]:
            context.orders.target_value(self.symbol, context.portfolio.cash * 0.99)

    def _signal(self, close: pd.Series) -> dict[str, float | bool] | None:
        if len(close) < 61:
            return None
        averages = {window: float(close.iloc[-window:].mean()) for window in (5, 10, 20, 60)}
        previous = {window: float(close.iloc[-window - 1:-1].mean()) for window in (5, 10, 20, 60)}
        price = float(close.iloc[-1])
        bullish = averages[5] > averages[10] > averages[20] > averages[60]
        bullish_previous = previous[5] > previous[10] > previous[20] > previous[60]
        slopes_up = averages[20] > previous[20] and averages[60] > previous[60]
        entry = bullish and bullish_previous and slopes_up and averages[20] < price < averages[20] * self.pullback_limit
        return {"close": price, "ma60": averages[60], "bullish": bullish, "entry": entry}

    def _should_exit(self, signal: dict[str, float | bool], average_cost: float | None) -> bool:
        if not signal["bullish"] or signal["close"] < signal["ma60"]:
            return True
        if average_cost is None or average_cost <= 0:
            return False
        returns = signal["close"] / average_cost - 1
        return bool(returns <= -self.stop_loss or returns >= self.take_profit)
