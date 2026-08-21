"""量价趋势（VPT）A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class VolumePriceTrendAShareEventStrategy:
    """VPT 上穿信号线且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "volume"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        signal_window: int = 10,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.signal_window = signal_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"VPT 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close", "volume"],
            self.trend_window + self.signal_window + 5,
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
        minimum = self.trend_window + self.signal_window + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            vpt = self._vpt(bars["close"], bars["volume"])
            signal = vpt.ewm(
                span=self.signal_window,
                adjust=False,
                min_periods=self.signal_window,
            ).mean()
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            values = [vpt.iloc[-2], vpt.iloc[-1], signal.iloc[-2], signal.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    vpt.iloc[-2] <= signal.iloc[-2]
                    and vpt.iloc[-1] > signal.iloc[-1]
                    and vpt.iloc[-1] > 0
                    and close > trend.iloc[-1]
                ),
                "exit": bool(
                    vpt.iloc[-1] < signal.iloc[-1]
                    or vpt.iloc[-1] < 0
                    or close < trend.iloc[-1]
                ),
                "score": float(vpt.iloc[-1] - signal.iloc[-1]),
            }
        return result

    @staticmethod
    def _vpt(close: pd.Series, volume: pd.Series) -> pd.Series:
        return (close.pct_change().fillna(0.0) * volume).cumsum()
