"""George Lane 风格 KD 随机指标 A 股日频策略。"""

from __future__ import annotations

import pandas as pd


class LaneStochasticAShareEventStrategy:
    """上升趋势内的超卖金叉策略；股票池与证券状态由数据面板预先过滤。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})
    required_market_state = frozenset({"suspended", "limit_up", "limit_down"})

    def __init__(self, benchmark_symbol: str = "000300.SH", universe: list[str] | None = None,
                 max_holdings: int = 10, single_weight: float = 0.09) -> None:
        self.benchmark_symbol = benchmark_symbol
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"KD 随机指标策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or [s for s in context.data.symbols if s != self.benchmark_symbol]
        symbols = list(dict.fromkeys(universe + list(holdings)))
        history = context.data.history(symbols, ["open", "high", "low", "close"], 150)
        benchmark = context.data.history([self.benchmark_symbol], ["close"], 120)["close"]
        metrics = self._metrics(history, symbols)
        survivors = self._exit_positions(context, metrics, holdings)
        if not self._market_allows_entry(benchmark):
            for symbol in survivors:
                context.orders.close(symbol)
            return
        slots = self.max_holdings - len(survivors)
        candidates = [(s, item["score"]) for s, item in metrics.items() if s not in holdings and item["entry"]]
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * metrics[s]["close"] for s in holdings if s in metrics)
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
            if len(bars) < 120:
                continue
            open_price, high, low, close = (bars[field] for field in ("open", "high", "low", "close"))
            k, d = self._stochastic(high, low, close)
            if pd.isna(k.iloc[-2]) or pd.isna(d.iloc[-2]) or pd.isna(k.iloc[-1]) or pd.isna(d.iloc[-1]):
                continue
            day_range = max(float(high.iloc[-1] - low.iloc[-1]), 1e-8)
            golden = k.iloc[-2] <= d.iloc[-2] and k.iloc[-1] > d.iloc[-1]
            dead = k.iloc[-2] >= d.iloc[-2] and k.iloc[-1] < d.iloc[-1] and max(k.iloc[-2], d.iloc[-2]) >= 70
            entry = (golden and min(k.iloc[-2], d.iloc[-2]) <= 20 and k.iloc[-1] <= 35
                     and close.iloc[-1] > close.iloc[-60:].mean() and close.iloc[-1] > open_price.iloc[-1]
                     and (close.iloc[-1] - low.iloc[-1]) / day_range >= 0.55)
            exit_signal = dead or close.iloc[-1] < close.iloc[-60:].mean() or close.iloc[-1] < low.iloc[-21:-1].min()
            result[symbol] = {"close": float(close.iloc[-1]), "entry": bool(entry), "exit": bool(exit_signal),
                              "score": float((35 - k.iloc[-1]) / 35 + max(close.iloc[-1] / close.iloc[-21] - 1, 0))}
        return result

    @staticmethod
    def _stochastic(high, low, close):
        highest, lowest = high.rolling(14).max(), low.rolling(14).min()
        fast_k = 100 * (close - lowest) / (highest - lowest).replace(0, float("nan"))
        slow_k = fast_k.rolling(3).mean()
        return slow_k, slow_k.rolling(3).mean()

    @staticmethod
    def _market_allows_entry(close):
        series = close.iloc[:, 0].dropna() if not close.empty else pd.Series(dtype=float)
        return bool(len(series) >= 120 and series.iloc[-1] > series.iloc[-120:].mean())
