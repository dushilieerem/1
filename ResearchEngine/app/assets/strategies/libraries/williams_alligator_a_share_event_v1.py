"""Williams Alligator A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class WilliamsAlligatorAShareEventStrategy:
    """以滞后平滑的 Jaw、Teeth、Lips 多头排列识别趋势。"""

    execution_mode = "event"
    required_fields = frozenset({"high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        jaw_window: int = 13,
        teeth_window: int = 8,
        lips_window: int = 5,
        jaw_shift: int = 8,
        teeth_shift: int = 5,
        lips_shift: int = 3,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.jaw_window = jaw_window
        self.teeth_window = teeth_window
        self.lips_window = lips_window
        self.jaw_shift = jaw_shift
        self.teeth_shift = teeth_shift
        self.lips_shift = lips_shift

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"Williams Alligator 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(
                self.jaw_window + self.jaw_shift,
                self.teeth_window + self.teeth_shift,
                self.lips_window + self.lips_shift,
            )
            + 5,
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
        minimum = max(
            self.jaw_window + self.jaw_shift,
            self.teeth_window + self.teeth_shift,
            self.lips_window + self.lips_shift,
        ) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            lines = self._alligator(
                bars["high"],
                bars["low"],
                bars["close"],
                self.jaw_window,
                self.teeth_window,
                self.lips_window,
                self.jaw_shift,
                self.teeth_shift,
                self.lips_shift,
            )
            latest = lines.iloc[-1]
            previous = lines.iloc[-2]
            if pd.isna(latest).any() or pd.isna(previous).any():
                continue
            close = float(bars["close"].iloc[-1])
            bullish = bool(
                latest["lips"] > latest["teeth"] > latest["jaw"]
                and close > latest["lips"]
            )
            previous_bullish = bool(
                previous["lips"] > previous["teeth"] > previous["jaw"]
                and bars["close"].iloc[-2] > previous["lips"]
            )
            result[symbol] = {
                "close": close,
                "entry": bool(bullish and not previous_bullish),
                "exit": not bullish,
                "score": float(
                    (latest["lips"] - latest["jaw"]) / max(abs(close), 1e-8)
                ),
            }
        return result

    @staticmethod
    def _smma(series: pd.Series, window: int) -> pd.Series:
        return series.ewm(
            alpha=1 / window,
            adjust=False,
            min_periods=window,
        ).mean()

    @classmethod
    def _alligator(
        cls,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        jaw_window: int = 13,
        teeth_window: int = 8,
        lips_window: int = 5,
        jaw_shift: int = 8,
        teeth_shift: int = 5,
        lips_shift: int = 3,
    ) -> pd.DataFrame:
        midpoint = (high + low) / 2
        return pd.DataFrame(
            {
                "jaw": cls._smma(midpoint, jaw_window).shift(jaw_shift),
                "teeth": cls._smma(midpoint, teeth_window).shift(teeth_shift),
                "lips": cls._smma(midpoint, lips_window).shift(lips_shift),
            },
            index=close.index,
        )
