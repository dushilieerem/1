"""商品通道指数（CCI）A 股日频均值回归策略。"""

from __future__ import annotations

import pandas as pd


class CciMeanReversionAShareEventStrategy:
    """长期趋势向上时，买入 CCI 从超卖区回升的现金多头组合。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        cci_window: int = 20,
        trend_window: int = 60,
        oversold: float = -100.0,
        overbought: float = 100.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.cci_window = cci_window
        self.trend_window = trend_window
        self.oversold = oversold
        self.overbought = overbought

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"CCI 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(self.cci_window, self.trend_window) + self.cci_window + 3,
        )
        metrics = self._metrics(history, symbols)

        survivors = set()
        for symbol in holdings:
            item = metrics.get(symbol)
            if item is None or item["exit"]:
                context.orders.close(symbol)
            else:
                survivors.add(symbol)

        slots = self.max_holdings - len(survivors)
        if slots <= 0:
            return
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(symbol) * metrics[symbol]["close"]
            for symbol in survivors
        )
        candidates = sorted(
            ((symbol, item["score"]) for symbol, item in metrics.items() if symbol not in holdings and item["entry"]),
            key=lambda item: item[1],
            reverse=True,
        )
        for symbol, _ in candidates[:slots]:
            context.orders.target_value(symbol, total_value * self.single_weight)

    def _metrics(self, history, symbols):
        result = {}
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < max(self.cci_window, self.trend_window) + 2:
                continue
            cci = self._cci(bars["high"], bars["low"], bars["close"], self.cci_window)
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([cci.iloc[-2], cci.iloc[-1], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    cci.iloc[-2] <= self.oversold
                    and cci.iloc[-1] > self.oversold
                    and close > trend.iloc[-1]
                ),
                "exit": bool(cci.iloc[-1] >= self.overbought or close < trend.iloc[-1]),
                "score": float(cci.iloc[-1] / 100.0 + close / trend.iloc[-1] - 1.0),
            }
        return result

    @staticmethod
    def _cci(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 20) -> pd.Series:
        typical_price = (high + low + close) / 3.0
        mean = typical_price.rolling(window, min_periods=window).mean()
        mean_deviation = typical_price.rolling(window, min_periods=window).apply(
            lambda values: float((abs(values - values.mean())).mean()), raw=True
        )
        return (typical_price - mean) / (0.015 * mean_deviation.replace(0, float("nan")))
