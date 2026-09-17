"""VR 成交量比率 A 股日频现金多头研究策略。"""

from __future__ import annotations

import pandas as pd


class VolumeRatioAShareEventStrategy:
    """以上涨、下跌和盘整成交量比率确认量价趋势的日频策略。"""

    execution_mode = "event"
    required_fields = frozenset({"close", "volume"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        window: int = 26,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.window = window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"VR A 股策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = {
            symbol
            for symbol, quantity in context.portfolio.positions.items()
            if quantity > 0
        }
        symbols = list(
            dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings))
        )
        lookback = max(self.window, self.trend_window) + 8
        history = context.data.history(symbols, ["close", "volume"], lookback)
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
        minimum = max(self.window, self.trend_window) + 2
        for symbol in symbols:
            raw = pd.DataFrame(
                {field: history[field][symbol] for field in history}
            )
            if (
                raw.empty
                or raw.iloc[-1].isna().any()
                or raw["close"].iloc[-1] <= 0
                or raw["volume"].iloc[-1] <= 0
            ):
                continue
            bars = raw.dropna()
            bars = bars[bars["volume"] > 0]
            if len(bars) < minimum:
                continue
            vr = self._vr(bars["close"], bars["volume"], self.window)
            trend = bars["close"].rolling(
                self.trend_window, min_periods=self.trend_window
            ).mean()
            values = [vr.iloc[-2], vr.iloc[-1], trend.iloc[-1]]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            vr_value = float(vr.iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    vr.iloc[-2] <= 1.0
                    and vr_value > 1.0
                    and close > trend.iloc[-1]
                ),
                "exit": bool(vr_value < 0.8 or close < trend.iloc[-1]),
                "score": float(vr_value - 1.0),
            }
        return result

    @staticmethod
    def _vr(
        close: pd.Series,
        volume: pd.Series,
        window: int = 26,
    ) -> pd.Series:
        """返回与情绪因子库一致的上涨/下跌/盘整成交量比率。"""
        change = close.diff()
        up = volume.where(change > 0, 0.0)
        down = volume.where(change < 0, 0.0)
        flat = volume.where(change == 0, 0.0)
        numerator = up.rolling(window, min_periods=window).sum()
        numerator = numerator + flat.rolling(window, min_periods=window).sum() / 2.0
        denominator = down.rolling(window, min_periods=window).sum()
        denominator = denominator + flat.rolling(window, min_periods=window).sum() / 2.0
        return numerator / denominator.where(denominator > 0)
