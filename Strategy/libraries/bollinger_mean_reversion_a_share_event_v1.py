"""John Bollinger 布林带 A 股日频回归策略的 SVQuant 事件策略版本。"""

from __future__ import annotations

import pandas as pd


class BollingerMeanReversionAShareEventStrategy:
    """上升趋势内下轨刺穿并收回的日频现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset({"open", "high", "low", "close"})
    required_market_state = frozenset({"suspended", "limit_up", "limit_down"})

    def __init__(
        self,
        benchmark_symbol: str = "000300.SH",
        universe: list[str] | None = None,
        max_holdings: int = 10,
        single_weight: float = 0.09,
        max_holding_calendar_days: int = 35,
    ) -> None:
        self.benchmark_symbol = benchmark_symbol
        self.universe = universe
        self.max_holdings = max_holdings
        self.single_weight = single_weight
        self.max_holding_calendar_days = max_holding_calendar_days

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"布林带 A 股策略缺少数据字段: {sorted(missing)}")
        context.state.entry_dates = {}
        context.state.last_scan_week = None
        context.schedule.daily(self.rebalance)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        context.state.entry_dates = {
            symbol: date for symbol, date in context.state.entry_dates.items() if symbol in holdings
        }
        for symbol in holdings:
            context.state.entry_dates.setdefault(symbol, context.current_dt.date())
        universe = self.universe or [symbol for symbol in context.data.symbols if symbol != self.benchmark_symbol]
        symbols = list(dict.fromkeys(universe + list(holdings)))
        history = context.data.history(symbols, ["open", "high", "low", "close"], 130)
        benchmark = context.data.history([self.benchmark_symbol], ["close"], 120)["close"]
        metrics = self._metrics(history, symbols)

        survivors = self._exit_positions(context, metrics, holdings)
        week_key = context.current_dt.isocalendar()[:2]
        if week_key == context.state.last_scan_week:
            return
        context.state.last_scan_week = week_key
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
            context.state.entry_dates[symbol] = context.current_dt.date()

    def _exit_positions(self, context, metrics, holdings):
        survivors = set()
        for symbol in holdings:
            item = metrics.get(symbol)
            held_days = (context.current_dt.date() - context.state.entry_dates[symbol]).days
            if item is None or item["exit"] or held_days >= self.max_holding_calendar_days:
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
            close, low, open_price = (bars[field] for field in ("close", "low", "open"))
            trend_ma = close.iloc[-120:].mean()
            current_bands = self._bands(close.iloc[-20:])
            entry_bands = self._bands(close.iloc[-21:-1])
            if current_bands is None or entry_bands is None:
                continue
            middle, _, lower, _ = current_bands
            _, upper_entry, lower_entry, bandwidth = entry_bands
            percent_b = (close.iloc[-1] - lower_entry) / max(upper_entry - lower_entry, 1e-8)
            reentry = low.iloc[-1] <= lower_entry and close.iloc[-1] > lower_entry
            trend_buffer = close.iloc[-1] / trend_ma - 1.0
            result[symbol] = {
                "close": float(close.iloc[-1]),
                "entry": bool(close.iloc[-1] > trend_ma and reentry and close.iloc[-1] > open_price.iloc[-1]
                              and 0 <= percent_b <= 0.35 and 0.04 <= bandwidth <= 0.35),
                "exit": bool(close.iloc[-1] >= middle or (close.iloc[-1] < lower and close.iloc[-1] < open_price.iloc[-1])
                             or close.iloc[-1] < trend_ma),
                "score": float(0.70 * (0.35 - percent_b) + 0.30 * min(max(trend_buffer, 0.0), 0.30)),
            }
        return result

    @staticmethod
    def _bands(close):
        if len(close) != 20:
            return None
        middle = float(close.mean())
        std = float(close.std(ddof=0))
        if middle <= 0 or std <= 1e-8:
            return None
        upper, lower = middle + 2 * std, middle - 2 * std
        return middle, upper, lower, (upper - lower) / middle

    @staticmethod
    def _market_allows_entry(close):
        series = close.iloc[:, 0].dropna() if not close.empty else pd.Series(dtype=float)
        return bool(len(series) >= 120 and series.iloc[-1] > series.iloc[-120:].mean())
