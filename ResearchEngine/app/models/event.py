"""事件回测的订单、成交与审计结果模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd


@dataclass
class EventOrder:
    symbol: str
    quantity: Optional[int] = None
    target_value: Optional[float] = None
    order_id: str = ""
    submitted_at: Optional[datetime] = None
    side: Optional[str] = None
    status: str = "submitted"
    reason_code: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.quantity is None) == (self.target_value is None):
            raise ValueError("订单必须且只能指定 quantity 或 target_value")


@dataclass(frozen=True)
class EventFill:
    order_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    timestamp: datetime
    commission: float
    stamp_tax: float


@dataclass(frozen=True)
class PositionSnapshot:
    timestamp: datetime
    cash: float
    positions: dict[str, int]
    sellable_quantities: dict[str, int]
    total_value: float


@dataclass
class EventBacktestResult:
    equity_curve: pd.Series
    orders: list[EventOrder] = field(default_factory=list)
    fills: list[EventFill] = field(default_factory=list)
    position_snapshots: list[PositionSnapshot] = field(default_factory=list)
    events: list[dict[str, object]] = field(default_factory=list)
    assumptions: dict[str, str] = field(default_factory=dict)

    @property
    def returns(self) -> pd.Series:
        return self.equity_curve.pct_change().dropna()


@dataclass(frozen=True)
class EventBacktestConfig:
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_tax_rate: float = 0.0005
    lot_size: int = 100


@dataclass
class _Ledger:
    cash: float
    positions: dict[str, int] = field(default_factory=dict)
    average_cost: dict[str, float] = field(default_factory=dict)
    sellable: dict[str, int] = field(default_factory=dict)
    bought_today: dict[str, int] = field(default_factory=dict)

    def begin_session(self) -> None:
        for symbol, quantity in self.bought_today.items():
            self.sellable[symbol] = self.sellable.get(symbol, 0) + quantity
        self.bought_today = {}


@dataclass
class PortfolioView:
    _ledger: object

    @property
    def cash(self) -> float:
        return self._ledger.cash

    @property
    def positions(self) -> dict[str, int]:
        return dict(self._ledger.positions)

    def quantity(self, symbol: str) -> int:
        return self._ledger.positions.get(symbol, 0)

    def average_cost(self, symbol: str) -> float | None:
        """返回当前持仓的成交均价；无持仓时返回 ``None``。"""
        return self._ledger.average_cost.get(symbol)
