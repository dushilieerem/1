"""约瑟夫·格兰维尔 OBV 能量潮 A 股事件策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class GranvilleObvAShareEventStrategy:
    """按行业截面评分的 OBV 量价趋势月度现金多头策略。"""

    execution_mode = "event"
    required_fields = frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "the_sw_industry_code",
            "pe_ttm",
            "pb_mrq",
            "current_mv",
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
        history_window: int = 121,
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
            raise ValueError(f"OBV 策略缺少数据字段: {sorted(missing)}")
        def rebalance_monthly(ctx):
            self.rebalance(ctx)

        context.schedule.monthly(rebalance_monthly, trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or list(context.data.symbols)
        symbols = list(dict.fromkeys([*universe, *holdings]))
        fields = [
            "close",
            "volume",
            "amount",
            "the_sw_industry_code",
            "pe_ttm",
            "pb_mrq",
            "current_mv",
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

            industry = history["the_sw_industry_code"][symbol].dropna()
            pe = pd.to_numeric(history["pe_ttm"][symbol], errors="coerce").dropna()
            pb = pd.to_numeric(history["pb_mrq"][symbol], errors="coerce").dropna()
            cap = pd.to_numeric(
                history["current_mv"][symbol], errors="coerce"
            ).dropna()
            if industry.empty or pe.empty or pb.empty or cap.empty:
                continue
            pe_value, pb_value, cap_value = float(pe.iloc[-1]), float(pb.iloc[-1]), float(cap.iloc[-1])
            if not 0 < pe_value <= 100 or not 0 < pb_value <= 15 or cap_value <= 0:
                continue

            close, volume = bars["close"], bars["volume"]
            if close.iloc[-61] <= 0 or volume.tail(60).mean() <= 0:
                continue
            obv = self._obv(close, volume)
            obv_ma20 = obv.rolling(20).mean().iloc[-1]
            x = np.arange(20, dtype=float)
            slope = np.polyfit(x, obv.iloc[-20:].to_numpy(dtype=float), 1)[0]
            avg_volume_20 = volume.tail(20).mean()
            avg_volume_60 = volume.tail(60).mean()
            obv_slope_norm = slope / avg_volume_20
            momentum_60 = close.iloc[-1] / close.iloc[-61] - 1.0
            volume_ratio = avg_volume_20 / avg_volume_60
            if not (
                close.iloc[-1] > close.tail(60).mean()
                and obv.iloc[-1] > obv_ma20
                and obv_slope_norm > 0
            ):
                continue
            values = [obv_slope_norm, momentum_60, volume_ratio]
            if not all(np.isfinite(value) for value in values):
                continue
            rows.append(
                (
                    symbol,
                    industry.iloc[-1],
                    cap_value,
                    bars["amount"].tail(20).mean(),
                    obv_slope_norm,
                    momentum_60,
                    volume_ratio,
                )
            )

        frame = pd.DataFrame(
            rows,
            columns=[
                "symbol",
                "industry",
                "cap",
                "avg_amount",
                "obv_slope_norm",
                "momentum_60",
                "volume_ratio",
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
            0.50 * frame.groupby("industry")["obv_slope_norm"].rank(pct=True)
            + 0.30 * frame.groupby("industry")["momentum_60"].rank(pct=True)
            + 0.20 * frame.groupby("industry")["volume_ratio"].rank(pct=True)
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
    def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        direction = np.sign(close.diff()).fillna(0.0)
        return (direction * volume).cumsum()
