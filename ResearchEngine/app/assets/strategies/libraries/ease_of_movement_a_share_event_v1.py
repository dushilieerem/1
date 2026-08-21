"""简化移动容易度（EOM）A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class EaseOfMovementAShareEventStrategy:
    """EOM 上穿零轴且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "volume"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        eom_window: int = 14,
        trend_window: int = 60,
        volume_divisor: float = 100_000_000.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.eom_window = eom_window
        self.trend_window = trend_window
        self.volume_divisor = volume_divisor

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"EOM 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close", "volume"],
            max(self.eom_window, self.trend_window) + self.eom_window + 3,
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
        minimum = max(self.eom_window, self.trend_window) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            eom = self._eom(
                bars["high"],
                bars["low"],
                bars["volume"],
                self.eom_window,
                self.volume_divisor,
            )
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([eom.iloc[-2], eom.iloc[-1], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(eom.iloc[-2] <= 0 and eom.iloc[-1] > 0 and close > trend.iloc[-1]),
                "exit": bool(eom.iloc[-1] < 0 or close < trend.iloc[-1]),
                "score": float(eom.iloc[-1] / max(abs(close), 1e-8)),
            }
        return result

    @staticmethod
    def _eom(
        high: pd.Series,
        low: pd.Series,
        volume: pd.Series,
        window: int = 14,
        volume_divisor: float = 100_000_000.0,
    ) -> pd.Series:
        midpoint = (high + low) / 2.0
        distance_moved = midpoint.diff()
        box_ratio = (volume / volume_divisor) / (high - low + 1e-10)
        one_period = distance_moved / (box_ratio + 1e-10)
        return one_period.rolling(window, min_periods=window).mean()
