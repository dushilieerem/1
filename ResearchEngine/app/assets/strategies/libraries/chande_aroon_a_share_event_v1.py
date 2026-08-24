"""Tushar Chande Aroon A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class ChandeAroonAShareEventStrategy:
    """Aroon 多头交叉与趋势确认的日频现金多头策略。"""

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
            raise ValueError(f"Aroon A 股策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or [s for s in context.data.symbols if s != self.benchmark_symbol]
        symbols = list(dict.fromkeys(universe + list(holdings)))
        history = context.data.history(symbols, ["open", "high", "low", "close"], 150)
        benchmark = context.data.history([self.benchmark_symbol], ["high", "low", "close"], 61)
        metrics = self._metrics(history, symbols)
        survivors = self._exit_positions(context, metrics, holdings)
        if not self._market_allows_entry(benchmark):
            for symbol in survivors:
                context.orders.close(symbol)
            return

        slots = self.max_holdings - len(survivors)
        candidates = [(s, item["score"]) for s, item in metrics.items() if s not in holdings and item["entry"]]
        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(s) * metrics[s]["close"] for s in holdings if s in metrics
        )
        for symbol, _ in sorted(candidates, key=lambda item: item[1], reverse=True)[:max(0, slots)]:
            context.orders.target_value(symbol, total_value * self.single_weight)

    def _exit_positions(self, context, metrics, holdings):
        survivors = set()
        for symbol in holdings:
            item = metrics.get(symbol)
            if item is None or item["exit"]:
                context.orders.close(symbol)
            else:
                survivors.add(symbol)
        return survivors

    def _metrics(self, history, symbols):
        result = {}
        for symbol in symbols:
            bars = pd.DataFrame({field: history[field][symbol] for field in history}).dropna()
            if len(bars) < 62:
                continue
            open_price, high, low, close = (bars[field] for field in ("open", "high", "low", "close"))
            up, down = self._aroon(high, low)
            up_prev, down_prev = self._aroon(high.iloc[:-1], low.iloc[:-1])
            if pd.isna([up, down, up_prev, down_prev]).any():
                continue
            day_range = max(float(high.iloc[-1] - low.iloc[-1]), 1e-8)
            cross = up_prev <= down_prev and up > down
            close_location = (close.iloc[-1] - low.iloc[-1]) / day_range
            quiet_days = ((high.iloc[-20:] - low.iloc[-20:]) / close.iloc[-20:] < 0.001).mean()
            entry = (
                cross and up >= 70 and down <= 30 and close.iloc[-1] > close.iloc[-60:].mean()
                and close.iloc[-1] > open_price.iloc[-1] and close_location >= 0.60
                and 3 <= close.iloc[-1] <= 300 and quiet_days <= 0.30
            )
            prior_lows = low.iloc[-21:-1]
            result[symbol] = {
                "close": float(close.iloc[-1]),
                "entry": bool(entry),
                "exit": bool(
                    (up_prev >= down_prev and up < down) or up < 50 or down > 50
                    or close.iloc[-1] < prior_lows.min()
                ),
                "score": float((up - down) / 100 + max(close.iloc[-1] / close.iloc[-61] - 1, 0)),
            }
        return result

    @staticmethod
    def _aroon(high, low):
        if len(high) < 26 or len(low) < 26:
            return float("nan"), float("nan")
        high_values, low_values = list(high.iloc[-26:]), list(low.iloc[-26:])
        high_age = next(i for i, value in enumerate(reversed(high_values)) if value == max(high_values))
        low_age = next(i for i, value in enumerate(reversed(low_values)) if value == min(low_values))
        return 100 * (25 - high_age) / 25, 100 * (25 - low_age) / 25

    def _market_allows_entry(self, history):
        bars = pd.DataFrame({field: history[field].iloc[:, 0] for field in history}).dropna()
        if len(bars) < 61:
            return False
        up, down = self._aroon(bars["high"], bars["low"])
        return bool(up > down and up >= 60 and bars["close"].iloc[-1] > bars["close"].iloc[-60:].mean())
