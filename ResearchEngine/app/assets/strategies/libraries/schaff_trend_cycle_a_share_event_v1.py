"""Schaff Trend Cycle A 股日频趋势动量策略。"""

from __future__ import annotations

import pandas as pd


class SchaffTrendCycleAShareEventStrategy:
    """使用双重随机平滑的 STC 和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        fast_window: int = 23,
        slow_window: int = 50,
        cycle_window: int = 10,
        smoothing_window: int = 3,
        trend_window: int = 60,
        entry_level: float = 25.0,
        exit_level: float = 75.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.cycle_window = cycle_window
        self.smoothing_window = smoothing_window
        self.trend_window = trend_window
        self.entry_level = entry_level
        self.exit_level = exit_level

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"STC 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = {
            symbol for symbol, quantity in context.portfolio.positions.items() if quantity > 0
        }
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(
                self.slow_window + 2 * self.cycle_window + 2 * self.smoothing_window,
                self.trend_window,
            )
            + 8,
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
        minimum = max(
            self.slow_window + 2 * self.cycle_window + 2 * self.smoothing_window,
            self.trend_window,
        ) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            close = bars["close"]
            stc = self._stc(
                close,
                self.fast_window,
                self.slow_window,
                self.cycle_window,
                self.smoothing_window,
            )
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_stc = stc.iloc[-1]
            previous_stc = stc.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna([latest_stc, previous_stc, latest_trend]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_stc = float(latest_stc)
            previous_stc = float(previous_stc)
            latest_trend = float(latest_trend)
            if latest_close <= 0:
                continue
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    previous_stc <= self.entry_level
                    and latest_stc > self.entry_level
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    (
                        previous_stc >= self.exit_level
                        and latest_stc < self.exit_level
                    )
                    or latest_stc < self.entry_level
                    or latest_close < latest_trend
                ),
                "score": latest_stc,
            }
        return result

    @staticmethod
    def _stc(
        close: pd.Series,
        fast_window: int = 23,
        slow_window: int = 50,
        cycle_window: int = 10,
        smoothing_window: int = 3,
    ) -> pd.Series:
        fast = close.ewm(span=fast_window, adjust=False, min_periods=fast_window).mean()
        slow = close.ewm(span=slow_window, adjust=False, min_periods=slow_window).mean()
        macd = fast - slow

        first_low = macd.rolling(cycle_window, min_periods=cycle_window).min()
        first_high = macd.rolling(cycle_window, min_periods=cycle_window).max()
        first_range = first_high - first_low
        first_value = (100 * (macd - first_low) / first_range).where(first_range > 0)
        first_smoothed = first_value.ewm(
            span=smoothing_window,
            adjust=False,
            min_periods=smoothing_window,
        ).mean()

        second_low = first_smoothed.rolling(cycle_window, min_periods=cycle_window).min()
        second_high = first_smoothed.rolling(cycle_window, min_periods=cycle_window).max()
        second_range = second_high - second_low
        second_value = (
            100 * (first_smoothed - second_low) / second_range
        ).where(second_range > 0)
        return second_value.ewm(
            span=smoothing_window,
            adjust=False,
            min_periods=smoothing_window,
        ).mean()
