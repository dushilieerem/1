"""韦尔斯·怀尔德 RSI 经典 A 股日频均值回归策略。"""

from __future__ import annotations

import pandas as pd


class WilderRsiClassicAShareEventStrategy:
    """只在长期趋势向上时买入 RSI 超卖后拐头的股票。

    日频引擎在当日开盘成交；止盈止损均以截至前一收盘的持仓均价判断。
    股票池的历史成分、ST、停牌和上市状态须由数据面板准备阶段处理。
    """

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})
    required_market_state = frozenset({"up_and_down_status"})
    execution_assumptions = frozenset({"daily_open", "no_slippage"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 3,
        rsi_period: int = 14,
        trend_window: int = 200,
        oversold: float = 30.0,
        overbought: float = 70.0,
        stop_loss: float = 0.08,
        take_profit: float = 0.20,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.rsi_period = rsi_period
        self.trend_window = trend_window
        self.oversold = oversold
        self.overbought = overbought
        self.stop_loss = stop_loss
        self.take_profit = take_profit

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Wilder RSI 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or context.data.symbols
        symbols = list(dict.fromkeys([*universe, *holdings]))
        history = context.data.history(symbols, ["close"], self.trend_window + self.rsi_period + 2)["close"]
        if len(history) < self.trend_window + 1:
            return

        candidates: list[tuple[str, float]] = []
        survivors: set[str] = set()
        for symbol in symbols:
            close = history[symbol].dropna()
            if len(close) < self.trend_window + 1:
                if symbol in holdings:
                    context.orders.close(symbol)
                continue
            rsi = self._rsi(close, self.rsi_period)
            if len(rsi) < 2:
                continue
            latest_rsi, previous_rsi = float(rsi.iloc[-1]), float(rsi.iloc[-2])
            latest_close = float(close.iloc[-1])
            if symbol in holdings:
                entry_price = context.portfolio.average_cost(symbol)
                if (
                    latest_rsi > self.overbought
                    or (entry_price is not None and latest_close <= entry_price * (1 - self.stop_loss))
                    or (entry_price is not None and latest_close >= entry_price * (1 + self.take_profit))
                ):
                    context.orders.close(symbol)
                else:
                    survivors.add(symbol)
                continue
            if (
                latest_rsi < self.oversold
                and latest_rsi > previous_rsi
                and latest_close > float(close.iloc[-self.trend_window:].mean())
            ):
                candidates.append((symbol, latest_rsi))

        slots = self.max_holdings - len(survivors)
        if slots <= 0:
            return
        candidates.sort(key=lambda item: item[1])
        target_value = context.portfolio.cash * 0.99 / slots
        for symbol, _ in candidates[:slots]:
            context.orders.target_value(symbol, target_value)

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gains = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)
        average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        relative_strength = average_gain / average_loss.replace(0, float("nan"))
        rsi = 100 - 100 / (1 + relative_strength)
        return rsi.where(average_loss > 0, 100.0)
