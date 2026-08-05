"""Gerald Appel MACD A 股日频趋势策略的 SVQuant 事件策略版本。"""

from __future__ import annotations

import pandas as pd


class AppelMacdAShareEventStrategy:
    """MACD 金叉、零轴与中期趋势确认的日频现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})
    required_market_state = frozenset({"suspended", "limit_up", "limit_down"})

    def __init__(
        self,
        benchmark_symbol: str = "000300.SH",
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
    ) -> None:
        self.benchmark_symbol = benchmark_symbol
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"MACD A 股策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or [symbol for symbol in context.data.symbols if symbol != self.benchmark_symbol]
        symbols = list(dict.fromkeys(universe + list(holdings)))
        history = context.data.history(symbols, ["open", "high", "low", "close"], 140)
        benchmark = context.data.history([self.benchmark_symbol], ["close"], 120)["close"]
        metrics = self._metrics(history, symbols)

        survivors = self._exit_positions(context, metrics, holdings)
        if not self._market_allows_entry(benchmark):
            return

        slots = self.max_holdings - len(survivors)
        if slots <= 0:
            return
        candidates = [
            (symbol, item["score"])
            for symbol, item in metrics.items()
            if symbol not in holdings and item["entry"]
        ]
        candidates.sort(key=lambda item: item[1], reverse=True)
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(symbol) * metrics[symbol]["close"]
            for symbol in holdings if symbol in metrics
        )
        for symbol, _ in candidates[:slots]:
            context.orders.target_value(symbol, total_value * self.single_weight)

    def _exit_positions(self, context, metrics, holdings):
        survivors = set()
        for symbol in holdings:
            item = metrics.get(symbol)
            if item is None or item["dead_cross"] or item["trend_failed"] or item["price_stop"]:
                context.orders.close(symbol)
            else:
                survivors.add(symbol)
        return survivors

    def _metrics(self, history, symbols):
        result = {}
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < 121:
                continue
            close, high, low, open_price = (bars[field] for field in ("close", "high", "low", "open"))
            ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
            ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
            dif = ema12 - ema26
            dea = dif.ewm(span=9, adjust=False, min_periods=9).mean()
            ema60 = close.ewm(span=60, adjust=False, min_periods=60).mean()
            if pd.isna(dea.iloc[-2]) or pd.isna(dea.iloc[-1]) or pd.isna(ema60.iloc[-1]):
                continue
            day_range = max(float(high.iloc[-1] - low.iloc[-1]), 1e-8)
            close_location = float((close.iloc[-1] - low.iloc[-1]) / day_range)
            golden_cross = dif.iloc[-2] <= dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]
            dead_cross = dif.iloc[-2] >= dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]
            price_stop = close.iloc[-1] < low.iloc[-21:-1].min()
            histogram = dif.iloc[-1] - dea.iloc[-1]
            momentum60 = close.iloc[-1] / close.iloc[-61] - 1.0
            result[symbol] = {
                "close": float(close.iloc[-1]),
                "entry": bool(golden_cross and dif.iloc[-1] > 0 and close.iloc[-1] > ema60.iloc[-1]
                              and close.iloc[-1] > open_price.iloc[-1] and close_location >= 0.60),
                "dead_cross": bool(dead_cross),
                "trend_failed": bool(close.iloc[-1] < ema60.iloc[-1]),
                "price_stop": bool(price_stop),
                "score": float(100.0 * histogram / close.iloc[-1] + max(momentum60, 0.0)),
            }
        return result

    @staticmethod
    def _market_allows_entry(close):
        series = close.iloc[:, 0].dropna() if not close.empty else pd.Series(dtype=float)
        if len(series) < 120:
            return False
        market_ema = series.ewm(span=120, adjust=False, min_periods=120).mean()
        return bool(series.iloc[-1] > market_ema.iloc[-1])
