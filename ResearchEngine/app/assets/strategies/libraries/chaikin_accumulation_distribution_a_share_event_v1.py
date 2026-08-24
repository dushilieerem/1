"""马克·蔡金累积派发与振荡器 A 股事件策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class ChaikinAccumulationDistributionAShareEventStrategy:
    """按行业截面评分的蔡金资金流月度现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "industry",
            "pe_ratio",
            "pb_ratio",
            "circulating_market_cap",
        }
    )

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 20,
        max_industry_holdings: int = 4,
        single_weight: float = 0.05,
        max_exposure: float = 0.95,
        hold_rank_buffer: int = 40,
        min_amount: float = 20_000_000.0,
        min_valid_days: int = 15,
        history_window: int = 81,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.max_industry_holdings = max_industry_holdings
        self.single_weight = single_weight
        self.max_exposure = max_exposure
        self.hold_rank_buffer = hold_rank_buffer
        self.min_amount = min_amount
        self.min_valid_days = min_valid_days
        self.history_window = history_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"蔡金策略缺少数据字段: {sorted(missing)}")
        def rebalance_monthly(ctx):
            self.rebalance(ctx)

        context.schedule.monthly(rebalance_monthly, trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or list(context.data.symbols)
        symbols = list(dict.fromkeys([*universe, *holdings]))
        fields = [
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "industry",
            "pe_ratio",
            "pb_ratio",
            "circulating_market_cap",
        ]
        history = context.data.history(symbols, fields, self.history_window)
        candidates = self._candidates(history, symbols)
        target = self._select(candidates, holdings)

        for symbol in holdings - set(target.index):
            context.orders.close(symbol)

        total_value = context.portfolio.cash + sum(
            context.portfolio.quantity(symbol)
            * float(history["close"][symbol].dropna().iloc[-1])
            for symbol in holdings
            if not history["close"][symbol].dropna().empty
        )
        if target.empty:
            return
        target_weight = min(self.single_weight, self.max_exposure / len(target))
        for symbol in target.index:
            context.orders.target_value(symbol, total_value * target_weight)

    def _candidates(self, history, symbols):
        rows = []
        for symbol in symbols:
            bars = pd.DataFrame(
                {
                    "high": pd.to_numeric(history["high"][symbol], errors="coerce"),
                    "low": pd.to_numeric(history["low"][symbol], errors="coerce"),
                    "close": pd.to_numeric(history["close"][symbol], errors="coerce"),
                    "volume": pd.to_numeric(history["volume"][symbol], errors="coerce"),
                    "amount": pd.to_numeric(history["amount"][symbol], errors="coerce"),
                }
            ).dropna()
            if len(bars) < self.history_window:
                continue
            if (
                bars["amount"].tail(20).gt(0).sum() < self.min_valid_days
                or bars["amount"].tail(20).mean() < self.min_amount
            ):
                continue

            industry = history["industry"][symbol].dropna()
            pe = pd.to_numeric(history["pe_ratio"][symbol], errors="coerce").dropna()
            pb = pd.to_numeric(history["pb_ratio"][symbol], errors="coerce").dropna()
            cap = pd.to_numeric(
                history["circulating_market_cap"][symbol], errors="coerce"
            ).dropna()
            if industry.empty or pe.empty or pb.empty or cap.empty:
                continue
            pe_value, pb_value, cap_value = float(pe.iloc[-1]), float(pb.iloc[-1]), float(cap.iloc[-1])
            if not 0 < pe_value <= 100 or not 0 < pb_value <= 15 or cap_value <= 0:
                continue

            high, low, close, volume = (
                bars["high"],
                bars["low"],
                bars["close"],
                bars["volume"],
            )
            if close.iloc[-61] <= 0 or volume.tail(20).sum() <= 0:
                continue
            multiplier, money_flow_volume, _, oscillator = self._chaikin(
                high, low, close, volume
            )
            cmf20 = money_flow_volume.tail(20).sum() / volume.tail(20).sum()
            oscillator_norm = oscillator.iloc[-1] / (volume.tail(20).mean() + 1.0)
            oscillator_change = oscillator.iloc[-1] - oscillator.iloc[-6]
            momentum_60 = close.iloc[-1] / close.iloc[-61] - 1.0
            if not (
                oscillator.iloc[-1] > 0
                and oscillator_change > 0
                and cmf20 > 0
                and close.iloc[-1] > close.tail(60).mean()
            ):
                continue
            values = [oscillator_norm, cmf20, momentum_60, float(multiplier.iloc[-1])]
            if not all(np.isfinite(value) for value in values):
                continue
            rows.append(
                (
                    symbol,
                    industry.iloc[-1],
                    cap_value,
                    bars["amount"].tail(20).mean(),
                    oscillator_norm,
                    cmf20,
                    momentum_60,
                )
            )

        frame = pd.DataFrame(
            rows,
            columns=[
                "symbol",
                "industry",
                "cap",
                "avg_amount",
                "oscillator_norm",
                "cmf20",
                "momentum_60",
            ],
        )
        if frame.empty:
            return frame
        frame = frame[frame["cap"] >= frame["cap"].quantile(0.05)].copy()
        counts = frame.groupby("industry")["symbol"].transform("count")
        frame = frame[counts >= 5].copy()
        if frame.empty:
            return frame
        frame["score"] = (
            0.50 * frame.groupby("industry")["oscillator_norm"].rank(pct=True)
            + 0.30 * frame.groupby("industry")["cmf20"].rank(pct=True)
            + 0.20 * frame.groupby("industry")["momentum_60"].rank(pct=True)
        )
        return frame.sort_values(["score", "avg_amount"], ascending=[False, False])

    def _select(self, candidates, holdings):
        if candidates.empty:
            return candidates.set_index("symbol")
        candidates = candidates.copy()
        candidates["global_rank"] = range(1, len(candidates) + 1)
        retained = candidates[
            candidates["symbol"].isin(holdings)
            & (candidates["global_rank"] <= self.hold_rank_buffer)
        ]
        ordered = pd.concat(
            [retained, candidates[~candidates["symbol"].isin(retained["symbol"])]]
        )
        selected, industry_count = [], {}
        for row in ordered.itertuples():
            used = industry_count.get(row.industry, 0)
            if used >= self.max_industry_holdings:
                continue
            selected.append(row.symbol)
            industry_count[row.industry] = used + 1
            if len(selected) >= self.max_holdings:
                break
        return candidates.set_index("symbol").loc[selected]

    @staticmethod
    def _chaikin(high, low, close, volume):
        spread = high - low
        multiplier = pd.Series(0.0, index=close.index)
        valid = spread.abs() > 1e-12
        multiplier.loc[valid] = (
            ((close - low) - (high - close)) / spread
        ).loc[valid]
        money_flow_volume = multiplier * volume
        ad_line = money_flow_volume.cumsum()
        oscillator = ad_line.ewm(span=3, adjust=False).mean() - ad_line.ewm(
            span=10, adjust=False
        ).mean()
        return multiplier, money_flow_volume, ad_line, oscillator
