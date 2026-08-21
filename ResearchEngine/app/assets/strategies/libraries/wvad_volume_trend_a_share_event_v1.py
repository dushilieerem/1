"""WVAD 威廉变异离散量 A 股日频量价趋势策略。"""

from __future__ import annotations

import pandas as pd


class WvadVolumeTrendAShareEventStrategy:
    """使用 WVAD 量价推动和长期均线过滤生成现金多头信号。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "volume"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        wvad_window: int = 24,
        trend_window: int = 60,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.wvad_window = wvad_window
        self.trend_window = trend_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"WVAD 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["open", "high", "low", "close", "volume"],
            max(self.wvad_window, self.trend_window) + 8,
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
        minimum = max(self.wvad_window, self.trend_window) + 3
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < minimum:
                continue
            open_ = bars["open"]
            high = bars["high"]
            low = bars["low"]
            close = bars["close"]
            volume = bars["volume"]
            wvad = self._wvad(open_, high, low, close, volume, self.wvad_window)
            trend = close.rolling(self.trend_window, min_periods=self.trend_window).mean()
            latest_wvad = wvad.iloc[-1]
            previous_wvad = wvad.iloc[-2]
            latest_trend = trend.iloc[-1]
            if pd.isna([latest_wvad, previous_wvad, latest_trend]).any():
                continue
            latest_close = float(close.iloc[-1])
            latest_wvad = float(latest_wvad)
            previous_wvad = float(previous_wvad)
            latest_trend = float(latest_trend)
            result[symbol] = {
                "close": latest_close,
                "entry": bool(
                    previous_wvad <= 0
                    and latest_wvad > 0
                    and latest_wvad > previous_wvad
                    and latest_close > latest_trend
                ),
                "exit": bool(
                    latest_wvad <= 0
                    or latest_close < latest_trend
                ),
                "score": latest_wvad,
            }
        return result

    @staticmethod
    def _wvad(
        open_: pd.Series,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
        window: int = 24,
    ) -> pd.Series:
        spread = high - low
        safe_spread = spread.where(spread.ne(0))
        raw = ((close - open_) / safe_spread * volume).where(spread.ne(0), 0.0)
        return raw.rolling(window, min_periods=window).sum()
