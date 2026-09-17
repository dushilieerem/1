"""Elder Ray Index A 股日频现金多头研究策略。"""

from __future__ import annotations

import pandas as pd


class ElderRayIndexAShareEventStrategy:
    """以 Elder Ray 牛力/熊力确认趋势的日频现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        ema_window: int = 13,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.ema_window = ema_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Elder Ray A 股策略缺少数据字段: {sorted(missing)}")
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
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(self.ema_window, self.trend_window) + 10,
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
        minimum = max(self.ema_window, self.trend_window) + 2
        for symbol in symbols:
            bars = pd.DataFrame(
                {field: history[field][symbol] for field in history}
            ).dropna()
            if len(bars) < minimum:
                continue
            indicators = self._elder_ray(
                bars["high"], bars["low"], bars["close"], self.ema_window
            )
            trend = bars["close"].rolling(
                self.trend_window, min_periods=self.trend_window
            ).mean()
            values = [
                indicators["ema"].iloc[-2],
                indicators["ema"].iloc[-1],
                indicators["bull_power"].iloc[-2],
                indicators["bull_power"].iloc[-1],
                indicators["bear_power"].iloc[-2],
                indicators["bear_power"].iloc[-1],
                trend.iloc[-1],
            ]
            if pd.isna(values).any():
                continue
            close = float(bars["close"].iloc[-1])
            ema = float(indicators["ema"].iloc[-1])
            bull_power = float(indicators["bull_power"].iloc[-1])
            bear_power = float(indicators["bear_power"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    indicators["bull_power"].iloc[-2] <= 0
                    and bull_power > 0
                    and ema > indicators["ema"].iloc[-2]
                    and bear_power > indicators["bear_power"].iloc[-2]
                    and close > trend.iloc[-1]
                ),
                "exit": bool(
                    close < ema
                    or bear_power < indicators["bear_power"].iloc[-2]
                    or close < trend.iloc[-1]
                ),
                "score": float(
                    (bull_power - bear_power) / max(abs(close), 1e-8)
                    + (ema - indicators["ema"].iloc[-2]) / max(abs(ema), 1e-8)
                ),
            }
        return result

    @staticmethod
    def _elder_ray(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        ema_window: int = 13,
    ) -> pd.DataFrame:
        ema = close.ewm(
            span=ema_window, adjust=False, min_periods=ema_window
        ).mean()
        return pd.DataFrame(
            {
                "ema": ema,
                "bull_power": high - ema,
                "bear_power": low - ema,
            },
            index=close.index,
        )
