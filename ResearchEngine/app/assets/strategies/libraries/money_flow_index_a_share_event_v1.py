"""资金流量指标（MFI）A 股日频量价策略。"""

from __future__ import annotations

import pandas as pd


class MoneyFlowIndexAShareEventStrategy:
    """MFI 从超卖区上穿且价格处于长期均线上方时做多。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "volume"})

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        mfi_window: int = 14,
        trend_window: int = 60,
        oversold: float = 20.0,
        overbought: float = 80.0,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.mfi_window = mfi_window
        self.trend_window = trend_window
        self.oversold = oversold
        self.overbought = overbought

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"MFI 策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        symbols = list(dict.fromkeys((self.universe or list(context.data.symbols)) + list(holdings)))
        history = context.data.history(
            symbols,
            ["high", "low", "close", "volume"],
            max(self.mfi_window, self.trend_window) + self.mfi_window + 3,
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
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < max(self.mfi_window, self.trend_window) + 2:
                continue
            mfi = self._mfi(
                bars["high"], bars["low"], bars["close"], bars["volume"], self.mfi_window
            )
            trend = bars["close"].rolling(self.trend_window, min_periods=self.trend_window).mean()
            if pd.isna([mfi.iloc[-2], mfi.iloc[-1], trend.iloc[-1]]).any():
                continue
            close = float(bars["close"].iloc[-1])
            result[symbol] = {
                "close": close,
                "entry": bool(
                    mfi.iloc[-2] <= self.oversold
                    and mfi.iloc[-1] > self.oversold
                    and close > trend.iloc[-1]
                ),
                "exit": bool(mfi.iloc[-1] >= self.overbought or close < trend.iloc[-1]),
                "score": float(mfi.iloc[-1] / 100.0 + close / trend.iloc[-1] - 1.0),
            }
        return result

    @staticmethod
    def _mfi(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
        window: int = 14,
    ) -> pd.Series:
        typical_price = (high + low + close) / 3.0
        raw_money_flow = typical_price * volume
        direction = typical_price.diff()
        positive_flow = raw_money_flow.where(direction > 0, 0.0)
        negative_flow = raw_money_flow.where(direction < 0, 0.0)
        positive_sum = positive_flow.rolling(window, min_periods=window).sum()
        negative_sum = negative_flow.rolling(window, min_periods=window).sum()
        ratio = positive_sum / negative_sum.replace(0, float("nan"))
        mfi = 100.0 - 100.0 / (1.0 + ratio)
        mfi = mfi.where(negative_sum > 0, 100.0)
        return mfi.where(~((positive_sum == 0) & (negative_sum == 0)), 50.0)
