"""净营运资产异象 A 股事件策略。"""

from __future__ import annotations

import numpy as np
import pandas as pd


class NetOperatingAssetsAnomalyAShareEventStrategy:
    """按净营运资产占比升序构建月度现金多头组合。"""

    execution_mode = "event"
    required_fields = frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "pe_ratio",
            "market_cap",
            "total_assets",
            "money_cap",
            "total_liabilities",
            "long_borr",
            "bond_payable",
        }
    )

    def __init__(
        self,
        universe: list[str] | None = None,
        max_holdings: int = 10,
        min_market_cap: float = 3_000_000_000.0,
        require_positive_earnings: bool = True,
        history_window: int = 260,
    ) -> None:
        self.universe = universe
        self.max_holdings = max_holdings
        self.min_market_cap = min_market_cap
        self.require_positive_earnings = require_positive_earnings
        self.history_window = history_window

    def initialize(self, context) -> None:
        missing = self.required_fields - context.data.fields
        if missing:
            raise ValueError(f"净营运资产异象策略缺少数据字段: {sorted(missing)}")
        def rebalance_monthly(ctx):
            self.rebalance(ctx)

        context.schedule.monthly(rebalance_monthly, trading_day=1)

    def rebalance(self, context) -> None:
        holdings = set(context.portfolio.positions)
        universe = self.universe or list(context.data.symbols)
        symbols = list(dict.fromkeys([*universe, *holdings]))
        fields = [
            "close",
            "pe_ratio",
            "market_cap",
            "total_assets",
            "money_cap",
            "total_liabilities",
            "long_borr",
            "bond_payable",
        ]
        history = context.data.history(symbols, fields, self.history_window)
        candidates = self._candidates(history, symbols)
        target = candidates.head(self.max_holdings).set_index("symbol") if not candidates.empty else candidates.set_index("symbol")

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
        target_value = total_value / self.max_holdings
        for symbol in target.index:
            context.orders.target_value(symbol, target_value)

    def _candidates(self, history, symbols):
        rows = []
        for symbol in symbols:
            values = {}
            for field in (
                "pe_ratio",
                "market_cap",
                "total_assets",
                "money_cap",
                "total_liabilities",
                "long_borr",
                "bond_payable",
            ):
                values[field] = pd.to_numeric(history[field][symbol], errors="coerce").dropna()
            close = pd.to_numeric(history["close"][symbol], errors="coerce").dropna()
            required_value_fields = (
                "market_cap",
                "total_assets",
                "money_cap",
                "total_liabilities",
                "long_borr",
                "bond_payable",
            )
            if close.empty or any(values[field].empty for field in required_value_fields):
                continue

            total_assets = float(values["total_assets"].iloc[-1])
            market_cap = float(values["market_cap"].iloc[-1])
            pe_ratio = float(values["pe_ratio"].iloc[-1]) if not values["pe_ratio"].empty else float("nan")
            if total_assets <= 0 or market_cap < self.min_market_cap:
                continue
            if self.require_positive_earnings and not (np.isfinite(pe_ratio) and pe_ratio > 0):
                continue

            money_cap = float(values["money_cap"].iloc[-1])
            total_liabilities = float(values["total_liabilities"].iloc[-1])
            long_borrowing = float(values["long_borr"].iloc[-1])
            bond_payable = float(values["bond_payable"].iloc[-1])
            noa = self._noa(total_assets, money_cap, total_liabilities, long_borrowing, bond_payable)
            if not np.isfinite(noa):
                continue
            rows.append((symbol, noa, market_cap, pe_ratio))
        return pd.DataFrame(rows, columns=["symbol", "noa", "market_cap", "pe_ratio"]).sort_values("noa", ascending=True)

    @staticmethod
    def _noa(total_assets, money_cap, total_liabilities, long_borrowing, bond_payable) -> float:
        operating_assets = total_assets - money_cap
        operating_liabilities = total_liabilities - long_borrowing - bond_payable
        return (operating_assets - operating_liabilities) / total_assets
