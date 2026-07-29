"""事件策略运行时：受限数据视图、调度器与订单服务。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Callable, Protocol

import pandas as pd

from quantcore.backtest.event.models import EventOrder


class EventStrategy(Protocol):
    def initialize(self, context: "StrategyContext") -> None: ...


class DataView:
    """仅暴露截至上一交易日收盘的日线数据。"""

    def __init__(self, panels: dict[str, pd.DataFrame]) -> None:
        self._panels = panels
        self._as_of: pd.Timestamp | None = None

    def set_as_of(self, timestamp: pd.Timestamp | None) -> None:
        self._as_of = timestamp

    @property
    def symbols(self) -> list[str]:
        return list(self._panels["close"].columns)

    @property
    def fields(self) -> frozenset[str]:
        return frozenset(self._panels)

    def history(self, symbols: list[str], fields: list[str], count: int) -> dict[str, pd.DataFrame]:
        if self._as_of is None:
            return {field: self._panels[field].iloc[0:0].reindex(columns=symbols) for field in fields}
        return {
            field: self._panels[field].loc[:self._as_of, symbols].tail(count).copy()
            for field in fields
        }


class Scheduler:
    def __init__(self) -> None:
        self._callbacks: dict[str, list[Callable[[StrategyContext], None]]] = defaultdict(list)

    def daily(self, callback: Callable[["StrategyContext"], None]) -> None:
        self._callbacks["daily"].append(callback)

    def weekly(self, callback: Callable[["StrategyContext"], None], weekday: int = 0) -> None:
        callback._event_weekday = weekday  # type: ignore[attr-defined]
        self._callbacks["weekly"].append(callback)

    def monthly(self, callback: Callable[["StrategyContext"], None], trading_day: int = 1) -> None:
        if trading_day < 1:
            raise ValueError("trading_day 必须从 1 开始")
        callback._event_trading_day = trading_day  # type: ignore[attr-defined]
        self._callbacks["monthly"].append(callback)

    def due(self, date: pd.Timestamp, trading_days: pd.DatetimeIndex) -> list[Callable[["StrategyContext"], None]]:
        callbacks = list(self._callbacks["daily"])
        callbacks.extend(
            callback for callback in self._callbacks["weekly"]
            if date.weekday() == callback._event_weekday  # type: ignore[attr-defined]
        )
        month_days = trading_days[trading_days.to_period("M") == date.to_period("M")]
        day_of_month = month_days.get_loc(date) + 1
        callbacks.extend(
            callback for callback in self._callbacks["monthly"]
            if day_of_month == callback._event_trading_day  # type: ignore[attr-defined]
        )
        return callbacks


class OrderService:
    def __init__(self) -> None:
        self._orders: list[EventOrder] = []
        self._sequence = 0
        self._current_dt: datetime | None = None

    @property
    def pending(self) -> list[EventOrder]:
        return self._orders

    def set_current_dt(self, current_dt: datetime) -> None:
        self._current_dt = current_dt

    def target_quantity(self, symbol: str, quantity: int) -> EventOrder:
        return self._submit(EventOrder(symbol=symbol, quantity=quantity))

    def target_value(self, symbol: str, value: float) -> EventOrder:
        return self._submit(EventOrder(symbol=symbol, target_value=value))

    def close(self, symbol: str) -> EventOrder:
        return self.target_value(symbol, 0.0)

    def _submit(self, order: EventOrder) -> EventOrder:
        self._sequence += 1
        order.order_id = f"EVT-{self._sequence:06d}"
        order.submitted_at = self._current_dt
        self._orders.append(order)
        return order


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


class StrategyContext:
    def __init__(self, data: DataView, orders: OrderService, portfolio: PortfolioView) -> None:
        self.current_dt: datetime | None = None
        self.state = SimpleNamespace()
        self.data = data
        self.orders = orders
        self.portfolio = portfolio
        self.schedule = Scheduler()
