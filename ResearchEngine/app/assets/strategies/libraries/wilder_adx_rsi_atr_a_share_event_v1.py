"""Wilder-inspired ADX/DMI、RSI、ATR A 股日频趋势策略。"""

from __future__ import annotations

import pandas as pd


class WilderAdxRsiAtrAShareEventStrategy:
    """日频现金多头策略；历史股票池、ST 与上市天数须在面板准备阶段过滤。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close", "amount"})
    required_market_state = frozenset({"up_and_down_status"})
    execution_assumptions = frozenset({"daily_open", "no_slippage"})

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
            raise ValueError(f"Wilder A 股策略缺少数据字段: {sorted(missing)}")
        context.state.peak_close = {}
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or [symbol for symbol in context.data.symbols if symbol != self.benchmark_symbol]
        symbols = list(dict.fromkeys(universe + list(holdings)))
        history = context.data.history(symbols, ["close", "high", "low", "amount"], 160)
        benchmark_history = context.data.history([self.benchmark_symbol], ["close"], 120)
        if len(history["close"]) < 120 or self.benchmark_symbol not in benchmark_history["close"]:
            return

        metrics = self._metrics(history, symbols)
        survivors = self._exit_positions(context, metrics, holdings)
        if not self._market_allows_entry(benchmark_history["close"]):
            return

        slots = self.max_holdings - len(survivors)
        if slots <= 0:
            return
        candidates = [
            (symbol, item["score"])
            for symbol, item in metrics.items()
            if symbol not in holdings
            and item["money20"] >= 30_000_000
            and item["atr_pct"] <= 0.08
            and item["plus_di"] > item["minus_di"]
            and item["adx"] >= 25
            and item["adx"] > item["adx_3"]
            and item["recent_bullish_cross"]
            and 50 <= item["rsi"] <= 70
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
            if item is None:
                context.orders.close(symbol)
                continue
            peak = max(context.state.peak_close.get(symbol, item["close"]), item["close"])
            context.state.peak_close[symbol] = peak
            atr_stop = peak - 3 * item["atr"]
            if item["minus_di"] > item["plus_di"] or item["adx"] < 20 or item["rsi"] < 40 or item["close"] < atr_stop:
                context.orders.close(symbol)
                context.state.peak_close.pop(symbol, None)
            else:
                survivors.add(symbol)
        return survivors

    def _metrics(self, history, symbols):
        result = {}
        for symbol in symbols:
            close = history["close"][symbol].dropna()
            high = history["high"][symbol].reindex(close.index)
            low = history["low"][symbol].reindex(close.index)
            money = history["amount"][symbol].reindex(close.index)
            if len(close) < 80 or high.isna().any() or low.isna().any() or money.isna().any():
                continue
            indicators = self._indicators(high, low, close)
            latest = indicators.iloc[-1]
            if latest.isna().any() or latest["atr"] <= 0 or latest["close"] <= 0:
                continue
            score = 0.50 * latest["adx"] / 100 + 0.35 * (latest["plus_di"] - latest["minus_di"]) / 100 + 0.15 * max(0.0, 1 - abs(latest["rsi"] - 60) / 20)
            crosses = (indicators["plus_di"] > indicators["minus_di"]) & (indicators["plus_di"].shift() <= indicators["minus_di"].shift())
            result[symbol] = {
                "close": float(latest["close"]), "atr": float(latest["atr"]),
                "atr_pct": float(latest["atr"] / latest["close"]),
                "plus_di": float(latest["plus_di"]), "minus_di": float(latest["minus_di"]),
                "adx": float(latest["adx"]), "adx_3": float(indicators["adx"].iloc[-4]),
                "rsi": float(latest["rsi"]), "money20": float(money.iloc[-20:].mean()),
                "recent_bullish_cross": bool(crosses.iloc[-5:].any()), "score": float(score),
            }
        return result

    def _indicators(self, high, low, close):
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = self._wilder(tr, 14)
        plus_di = 100 * self._wilder(plus_dm, 14) / atr
        minus_di = 100 * self._wilder(minus_dm, 14) / atr
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = self._wilder(dx, 14)
        delta = close.diff()
        gain = self._wilder(delta.clip(lower=0), 14)
        loss = self._wilder((-delta).clip(lower=0), 14)
        rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
        rsi = rsi.where(loss > 0, 100.0)
        return pd.DataFrame({"close": close, "atr": atr, "plus_di": plus_di, "minus_di": minus_di, "adx": adx, "rsi": rsi})

    @staticmethod
    def _wilder(values, window):
        return values.ewm(alpha=1 / window, adjust=False).mean()

    def _market_allows_entry(self, close):
        benchmark = close[self.benchmark_symbol].dropna()
        return len(benchmark) >= 120 and benchmark.iloc[-1] > benchmark.iloc[-120:].mean()
