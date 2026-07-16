"""``Order`` / ``Fill`` - 订单与成交回报。

依据 ``docs/04-features/FEAT-001-quantcore-core/04-class-design.md`` BacktestEngine 节。
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


_order_seq = itertools.count(1)


@dataclass
class Order:
    """订单。

    Attributes
    ----------
    symbol : str
        标的代码。
    direction : int
        方向，``1`` 买入，``-1`` 卖出。
    quantity : float
        委托数量。
    order_type : str
        ``"market"`` 市价单 / ``"limit"`` 限价单。
    price : float | None
        限价单价格；市价单为 ``None``。
    status : str
        ``"pending"`` / ``"filled"`` / ``"partial"`` / ``"cancelled"``。
    create_time : datetime
        创建时间。
    order_id : str
        订单 ID（自动生成）。
    """

    symbol: str
    direction: int
    quantity: float
    order_type: str = "market"
    price: Optional[float] = None
    status: str = "pending"
    create_time: datetime = field(default_factory=datetime.now)
    order_id: str = field(default_factory=lambda: f"ORD-{next(_order_seq):06d}")

    def __post_init__(self) -> None:
        if self.direction not in (1, -1):
            raise ValueError(f"direction 必须为 1(买) 或 -1(卖)，得到 {self.direction}")
        if self.order_type not in ("market", "limit"):
            raise ValueError(f"order_type 必须为 market/limit，得到 {self.order_type!r}")
        if self.order_type == "limit" and self.price is None:
            raise ValueError("限价单必须指定 price")


@dataclass
class Fill:
    """成交回报。"""

    order_id: str
    symbol: str
    direction: int
    fill_price: float
    fill_quantity: float
    fill_time: datetime
    commission: float = 0.0
    slippage: float = 0.0
    fill_id: str = field(default_factory=lambda: f"FILL-{uuid.uuid4().hex[:8]}")
