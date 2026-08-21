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
