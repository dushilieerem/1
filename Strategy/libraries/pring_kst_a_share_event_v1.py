"""Martin Pring KST A 股日频多周期动量策略。"""

from __future__ import annotations

import pandas as pd


class PringKstAShareEventStrategy:
    """负值区 KST 金叉与趋势确认的日频现金多头策略。"""

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
            raise ValueError(f"KST A 股策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or [s for s in context.data.symbols if s != self.benchmark_symbol]
        symbols = list(dict.fromkeys(universe + list(holdings)))
        history = context.data.history(symbols, ["open", "high", "low", "close"], 170)
        benchmark = context.data.history([self.benchmark_symbol], ["close"], 120)["close"]
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
            if len(bars) < 121:
                continue
            open_price, high, low, close = (bars[field] for field in ("open", "high", "low", "close"))
            kst, signal = self._kst(close)
            if pd.isna([kst.iloc[-2], kst.iloc[-1], signal.iloc[-2], signal.iloc[-1]]).any():
                continue
            day_range = max(float(high.iloc[-1] - low.iloc[-1]), 1e-8)
            golden = kst.iloc[-2] <= signal.iloc[-2] and kst.iloc[-1] > signal.iloc[-1]
            close_location = (close.iloc[-1] - low.iloc[-1]) / day_range
            quiet_days = ((high.iloc[-20:] - low.iloc[-20:]) / close.iloc[-20:] < 0.001).mean()
            entry = (
                golden and min(kst.iloc[-2], signal.iloc[-2]) < 0 and close.iloc[-1] > close.iloc[-60:].mean()
                and close.iloc[-1] > open_price.iloc[-1] and close_location >= 0.60
                and 3 <= close.iloc[-1] <= 300 and quiet_days <= 0.30
            )
            prior_lows = low.iloc[-21:-1]
            result[symbol] = {
                "close": float(close.iloc[-1]),
                "entry": bool(entry),
                "exit": bool(
                    (kst.iloc[-2] >= signal.iloc[-2] and kst.iloc[-1] < signal.iloc[-1])
                    or close.iloc[-1] < close.iloc[-60:].mean() or close.iloc[-1] < prior_lows.min()
                ),
                "score": float(max(kst.iloc[-1] - kst.iloc[-2], 0) / 100 + max(close.iloc[-1] / close.iloc[-61] - 1, 0)),
            }
        return result

    @staticmethod
    def _kst(close):
        price = pd.Series(close, dtype=float)
        components = [
            (100 * (price / price.shift(roc) - 1)).rolling(sma).mean()
            for roc, sma in zip((10, 15, 20, 30), (10, 10, 10, 15))
        ]
        kst = components[0] + 2 * components[1] + 3 * components[2] + 4 * components[3]
        return kst, kst.rolling(9).mean()

    @staticmethod
    def _market_allows_entry(close):
        series = close.iloc[:, 0].dropna() if not close.empty else pd.Series(dtype=float)
        return bool(len(series) >= 120 and series.iloc[-1] > series.iloc[-120:].mean())
