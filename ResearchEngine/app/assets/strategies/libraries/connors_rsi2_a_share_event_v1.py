"""Larry Connors RSI(2) A 股日频均值回归策略。"""

from __future__ import annotations

import pandas as pd


class ConnorsRsi2AShareEventStrategy:
    """长期趋势向上时，使用 RSI(2) 超卖反弹做多。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        rsi_period: int = 2,
        trend_window: int = 200,
        exit_window: int = 5,
        oversold: float = 10.0,
        overbought: float = 70.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.rsi_period = rsi_period
        self.trend_window = trend_window
        self.exit_window = exit_window
        self.oversold = oversold
        self.overbought = overbought

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Connors RSI(2) 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.trend_window, self.exit_window) + self.rsi_period + 4,
        )
        metrics = self._metrics(history, symbols)

        survivors = set()
        for symbol in holdings:
            item = metrics.get(symbol)
            if item is None or item["exit"]:
                context.orders.close(symbol)
            else:
                survivors.add(symbol)

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
        minimum = max(self.trend_window, self.exit_window) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            close = bars["close"]
            rsi = self._rsi(close, self.rsi_period)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            exit_average = close.rolling(self.exit_window, min_periods=self.exit_window).mean()
            latest_rsi = rsi.iloc[-1]
            latest_trend = trend.iloc[-1]
            latest_exit_average = exit_average.iloc[-1]
            if pd.isna([latest_rsi, latest_trend, latest_exit_average]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_rsi = float(latest_rsi)
            latest_trend = float(latest_trend)
            latest_exit_average = float(latest_exit_average)
            result[symbol] = {
                "close": latest_close,
                "entry": bool(latest_rsi <= self.oversold and latest_close > latest_trend),
                "exit": bool(
                    latest_rsi >= self.overbought
                    or latest_close > latest_exit_average
                    or latest_close < latest_trend
                ),
                "score": float(self.oversold - latest_rsi),
            }
        return result

    @staticmethod
    def _rsi(close: pd.Series, period: int = 2) -> pd.Series:
        delta = close.diff()
        gains = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)
        average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        relative_strength = average_gain / average_loss.replace(0, float("nan"))
        rsi = 100 - 100 / (1 + relative_strength)
        return rsi.where(average_loss > 0, 100.0)
