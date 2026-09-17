"""真实强度指数（TSI）A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class TrueStrengthIndexAShareEventStrategy:
    """TSI 上穿信号线且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        long_window: int = 25,
        short_window: int = 13,
        signal_window: int = 9,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.long_window = long_window
        self.short_window = short_window
        self.signal_window = signal_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"TSI 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.trend_window, self.long_window, self.short_window, self.signal_window) + 4,
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
            self.long_window,
            self.short_window,
            self.signal_window,
        ) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            tsi = self._true_strength_index(
                bars["close"],
                self.long_window,
                self.short_window,
            )
            signal = tsi.ewm(
                span=self.signal_window,
                adjust=False,
                min_periods=self.signal_window,
            ).mean()
            trend = bars["close"].rolling(
                self.trend_window,
                min_periods=self.trend_window,
            ).mean()
            if any(
                pd.isna(value)
                for value in (tsi.iloc[-2], tsi.iloc[-1], signal.iloc[-2], signal.iloc[-1], trend.iloc[-1])
            ):
                continue
            close = float(bars["close"].iloc[-1])
            trend_value = float(trend.iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    tsi.iloc[-2] <= signal.iloc[-2]
                    and tsi.iloc[-1] > signal.iloc[-1]
                    and tsi.iloc[-1] > 0
                    and close > trend_value
                ),
                "exit": bool(tsi.iloc[-1] < signal.iloc[-1] or close < trend_value),
                "score": float(tsi.iloc[-1] - signal.iloc[-1]),
            }
        return result

    @staticmethod
    def _true_strength_index(
        close: pd.Series,
        long_window: int = 25,
        short_window: int = 13,
    ) -> pd.Series:
        momentum = close.diff()
        smooth_momentum = momentum.ewm(
            span=long_window,
            adjust=False,
        ).mean().ewm(span=short_window, adjust=False).mean()
        smooth_absolute = momentum.abs().ewm(
            span=long_window,
            adjust=False,
        ).mean().ewm(span=short_window, adjust=False).mean()
        return 100 * smooth_momentum / (smooth_absolute + 1e-10)
