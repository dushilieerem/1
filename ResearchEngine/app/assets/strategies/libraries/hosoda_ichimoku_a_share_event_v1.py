"""细田悟一一目均衡表 A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class HosodaIchimokuAShareEventStrategy:
    """云层突破趋势策略；云层位移严格使用截至前一日可见的 OHLC 数据。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})
    required_market_state = frozenset({"suspended", "limit_up", "limit_down"})

    def __init__(self, benchmark_symbol: str = "000300.SH", universe: list[str] | None = None,
                 max_holdings: int = 10, single_weight: float = 0.09) -> None:
        self.benchmark_symbol, self.universe = benchmark_symbol, universe
        self.max_holdings, self.single_weight = max_holdings, single_weight

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"一目均衡表策略缺少数据字段: {sorted(missing)}")
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or [s for s in context.data.symbols if s != self.benchmark_symbol]
        symbols = list(dict.fromkeys(universe + list(holdings)))
        history = context.data.history(symbols, ["open", "high", "low", "close"], 110)
        benchmark = context.data.history([self.benchmark_symbol], ["high", "low", "close"], 110)
        metrics = self._metrics(history, symbols)
        survivors = self._exit_positions(context, metrics, holdings)
        if not self._market_allows_entry(benchmark):
            for symbol in survivors:
                context.orders.close(symbol)
            return
        candidates = [(s, item["score"]) for s, item in metrics.items() if s not in holdings and item["entry"]]
        total_value = context.portfolio.cash + sum(context.portfolio.quantity(s) * metrics[s]["close"] for s in holdings if s in metrics)
        for symbol, _ in sorted(candidates, key=lambda item: item[1], reverse=True)[:max(0, self.max_holdings - len(survivors))]:
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
            if len(bars) < 78:
                continue
            state = self._state(bars["high"], bars["low"], bars["close"])
            if state is None:
                continue
            close, open_price, high, low = (bars[field].iloc[-1] for field in ("close", "open", "high", "low"))
            cross_up = state["tenkan_prev"] <= state["kijun_prev"] and state["tenkan"] > state["kijun"]
            cross_down = state["tenkan_prev"] >= state["kijun_prev"] and state["tenkan"] < state["kijun"]
            cloud_top, cloud_bottom = max(state["cloud_a"], state["cloud_b"]), min(state["cloud_a"], state["cloud_b"])
            quiet_ratio = ((bars["high"].iloc[-20:] - bars["low"].iloc[-20:]) / bars["close"].iloc[-20:] < .001).mean()
            entry = (3 <= close <= 300 and quiet_ratio <= .30 and cross_up and close > cloud_top
                     and state["projected_a"] > state["projected_b"] and close > state["chikou"] and close > open_price)
            exit_signal = cross_down or close < state["kijun"] or close < cloud_bottom
            result[symbol] = {"close": float(close), "entry": bool(entry), "exit": bool(exit_signal),
                              "score": float(min(close / cloud_top - 1, .30) + 2 * max(state["tenkan"] / state["kijun"] - 1, 0))}
        return result

    @staticmethod
    def _state(high, low, close):
        if len(close) < 78:
            return None
        midpoint = lambda h, l, period: (h.iloc[-period:].max() + l.iloc[-period:].min()) / 2
        tenkan, kijun = midpoint(high, low, 9), midpoint(high, low, 26)
        past_high, past_low = high.iloc[:-26], low.iloc[:-26]
        cloud_a = (midpoint(past_high, past_low, 9) + midpoint(past_high, past_low, 26)) / 2
        return {"tenkan": tenkan, "kijun": kijun, "tenkan_prev": midpoint(high.iloc[:-1], low.iloc[:-1], 9),
                "kijun_prev": midpoint(high.iloc[:-1], low.iloc[:-1], 26), "cloud_a": cloud_a,
                "cloud_b": midpoint(past_high, past_low, 52), "projected_a": (tenkan + kijun) / 2,
                "projected_b": midpoint(high, low, 52), "chikou": close.iloc[-27]}

    @classmethod
    def _market_allows_entry(cls, history):
        if history["close"].empty:
            return False
        bars = pd.DataFrame({field: history[field].iloc[:, 0] for field in ("high", "low", "close")}).dropna()
        state = cls._state(bars["high"], bars["low"], bars["close"])
        return bool(state and bars["close"].iloc[-1] > max(state["cloud_a"], state["cloud_b"])
                    and state["projected_a"] > state["projected_b"])
