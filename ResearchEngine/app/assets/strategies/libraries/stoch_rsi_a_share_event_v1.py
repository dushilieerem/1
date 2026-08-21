"""随机 RSI（StochRSI）A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class StochRsiAShareEventStrategy:
    """StochRSI 从超卖区上穿且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        rsi_window: int = 14,
        stochastic_window: int = 14,
        trend_window: int = 60,
        oversold: float = 0.2,
        overbought: float = 0.8,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.rsi_window = rsi_window
        self.stochastic_window = stochastic_window
        self.trend_window = trend_window
        self.oversold = oversold
        self.overbought = overbought

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"StochRSI 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(
                self.trend_window + 3,
                self.rsi_window + self.stochastic_window + 4,
            ),
        )
        metrics = self._metrics(history, symbols)

        survivors = set()
        for symbol in holdings:
            item = metrics.get(symbol)
            if item is None or item["exit"]:
                context.orders.close(symbol)
            else:
                survivors.add(symbol)

        # 持仓当日可能受 T+1 约束无法立即卖出，因此名额按现有持仓计算，避免超出上限。
        slots = self.max_holdings - len(holdings)
        if slots <= 0:
            return
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(symbol) * metrics[symbol]["close"]
            for symbol in survivors
        )
        candidates = sorted(
            (
                (symbol, item["score"])
                for symbol, item in metrics.items()
                if symbol not in holdings and item["entry"]
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        for symbol, _ in candidates[:slots]:
            context.orders.target_value(symbol, total_value * self.single_weight)

    def _metrics(self, history, symbols):
        result = {}
        minimum = max(
            self.trend_window,
            self.rsi_window + self.stochastic_window,
        ) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            stoch_rsi = self._stoch_rsi(
                bars["close"],
                self.rsi_window,
                self.stochastic_window,
            )
            trend = bars["close"].rolling(
                self.trend_window,
                min_periods=self.trend_window,
            ).mean()
            if any(pd.isna(value) for value in (stoch_rsi.iloc[-2], stoch_rsi.iloc[-1], trend.iloc[-1])):
                continue
            close = float(bars["close"].iloc[-1])
            trend_value = float(trend.iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    stoch_rsi.iloc[-2] <= self.oversold
                    and stoch_rsi.iloc[-1] > self.oversold
                    and close > trend_value
                ),
                "exit": bool(stoch_rsi.iloc[-1] >= self.overbought or close < trend_value),
                "score": float(stoch_rsi.iloc[-1] - self.oversold),
            }
        return result

    @staticmethod
    def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = -delta.clip(upper=0).rolling(window).mean()
        rs = gain / (loss + 1e-10)
        return 100 - 100 / (1 + rs)

    @classmethod
    def _stoch_rsi(
        cls,
        close: pd.Series,
        rsi_window: int = 14,
        stochastic_window: int = 14,
    ) -> pd.Series:
        rsi = cls._rsi(close, rsi_window)
        highest = rsi.rolling(stochastic_window).max()
        lowest = rsi.rolling(stochastic_window).min()
        return (rsi - lowest) / (highest - lowest + 1e-10)
