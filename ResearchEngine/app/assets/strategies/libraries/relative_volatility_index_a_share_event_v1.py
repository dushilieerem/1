"""相对波动指数（RVI）A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class RelativeVolatilityIndexAShareEventStrategy:
    """RVI 上穿 50 且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        volatility_window: int = 10,
        smooth_window: int = 14,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.volatility_window = volatility_window
        self.smooth_window = smooth_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"相对波动指数策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.trend_window, self.volatility_window, self.smooth_window) + 4,
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
            self.volatility_window,
            self.smooth_window,
        ) + 2
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            rvi = self._relative_volatility_index(
                bars["close"],
                self.volatility_window,
                self.smooth_window,
            )
            trend = bars["close"].rolling(
                self.trend_window,
                min_periods=self.trend_window,
            ).mean()
            if any(pd.isna(value) for value in (rvi.iloc[-2], rvi.iloc[-1], trend.iloc[-1])):
                continue
            close = float(bars["close"].iloc[-1])
            trend_value = float(trend.iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    rvi.iloc[-2] <= 50
                    and rvi.iloc[-1] > 50
                    and close > trend_value
                ),
                "exit": bool(rvi.iloc[-1] < 50 or close < trend_value),
                "score": float(rvi.iloc[-1] - 50),
            }
        return result

    @staticmethod
    def _relative_volatility_index(
        close: pd.Series,
        volatility_window: int = 10,
        smooth_window: int = 14,
    ) -> pd.Series:
        volatility = close.rolling(volatility_window).std(ddof=0)
        direction = close.diff()
        upside = volatility.where(direction > 0, 0.0)
        downside = volatility.where(direction < 0, 0.0)
        upside = upside.ewm(span=smooth_window, adjust=False).mean()
        downside = downside.ewm(span=smooth_window, adjust=False).mean()
        return 100 * upside / (upside + downside + 1e-10)
