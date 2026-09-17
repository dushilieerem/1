"""SMI 随机动量指标 A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class StochasticMomentumIndexAShareEventStrategy:
    """使用 SMI 信号线交叉和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"high", "low", "close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        smi_window: int = 14,
        smoothing_window: int = 3,
        signal_window: int = 3,
        trend_window: int = 60,
        entry_ceiling: float = 0.0,
        exit_level: float = 40.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.smi_window = smi_window
        self.smoothing_window = smoothing_window
        self.signal_window = signal_window
        self.trend_window = trend_window
        self.entry_ceiling = entry_ceiling
        self.exit_level = exit_level

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"SMI 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = {
            symbol for symbol, quantity in context.portfolio.positions.items() if quantity > 0
        }
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close"],
            max(
                self.smi_window + 2 * self.smoothing_window + self.signal_window,
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
            self.smi_window + 2 * self.smoothing_window + self.signal_window,
            self.trend_window,
        ) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            high = bars["high"]
            low = bars["low"]
            close = bars["close"]
            smi = self._smi(
                high,
                low,
                close,
                self.smi_window,
                self.smoothing_window,
            )
            signal = self._signal(smi, self.signal_window)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_smi = smi.iloc[-1]
            previous_smi = smi.iloc[-2]
            latest_signal = signal.iloc[-1]
            previous_signal = signal.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna(
                [
                    latest_smi,
                    previous_smi,
                    latest_signal,
                    previous_signal,
                    latest_trend,
                ]
            ).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_smi = float(latest_smi)
            previous_smi = float(previous_smi)
            latest_signal = float(latest_signal)
            previous_signal = float(previous_signal)
            latest_trend = float(latest_trend)
            if latest_close <= 0:
                continue
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    previous_smi <= previous_signal
                    and latest_smi > latest_signal
                    and latest_smi < self.entry_ceiling
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    (
                        previous_smi >= previous_signal
                        and latest_smi < latest_signal
                    )
                    or latest_smi >= self.exit_level
                    or latest_close < latest_trend
                ),
                "score": float(latest_smi - latest_signal),
            }
        return result

    @staticmethod
    def _smi(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 14,
        smoothing_window: int = 3,
    ) -> pd.Series:
        highest = high.rolling(window, min_periods=window).max()
        lowest = low.rolling(window, min_periods=window).min()
        midpoint = (highest + lowest) / 2
        half_range = (highest - lowest) / 2
        distance = close - midpoint
        smooth_distance = distance.ewm(
            span=smoothing_window,
            adjust=False,
            min_periods=smoothing_window,
        ).mean().ewm(
            span=smoothing_window,
            adjust=False,
            min_periods=smoothing_window,
        ).mean()
        smooth_range = half_range.ewm(
            span=smoothing_window,
            adjust=False,
            min_periods=smoothing_window,
        ).mean().ewm(
            span=smoothing_window,
            adjust=False,
            min_periods=smoothing_window,
        ).mean()
        return 100 * smooth_distance / smooth_range.where(smooth_range.ne(0))

    @staticmethod
    def _signal(smi: pd.Series, signal_window: int = 3) -> pd.Series:
        return smi.ewm(
            span=signal_window,
            adjust=False,
            min_periods=signal_window,
        ).mean()
