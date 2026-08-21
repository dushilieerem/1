"""VHF 纵横指标 A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class VhfTrendAShareEventStrategy:
    """使用 VHF 趋势强度和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"close"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        vhf_window: int = 28,
        trend_window: int = 60,
        entry_threshold: float = 0.4,
        exit_threshold: float = 0.3,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.vhf_window = vhf_window
        self.trend_window = trend_window
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"VHF 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["close"],
            max(self.vhf_window, self.trend_window) + 8,
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
        minimum = max(self.vhf_window, self.trend_window) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            close = bars["close"]
            vhf = self._vhf(close, self.vhf_window)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_vhf = vhf.iloc[-1]
            previous_vhf = vhf.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna([latest_vhf, previous_vhf, latest_trend]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_vhf = float(latest_vhf)
            previous_vhf = float(previous_vhf)
            latest_trend = float(latest_trend)
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    previous_vhf <= self.entry_threshold
                    and latest_vhf > self.entry_threshold
                    and latest_vhf > previous_vhf
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_vhf < self.exit_threshold
                    or latest_close < latest_trend
                ),
                "score": latest_vhf,
            }
        return result

    @staticmethod
    def _vhf(close: pd.Series, window: int = 28) -> pd.Series:
        numerator = close.rolling(window, min_periods=window).max() - close.rolling(
            window, min_periods=window
        ).min()
        denominator = close.diff().abs().rolling(window, min_periods=window).sum()
        return numerator / denominator.where(denominator.ne(0))
