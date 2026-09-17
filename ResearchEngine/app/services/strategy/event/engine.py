"""A 股现金多头的日频 EventEngine MVP。"""

from __future__ import annotations

import re

from app.models.event import EventBacktestConfig, _Ledger
from datetime import datetime

import pandas as pd

from app.models.event import EventBacktestResult, EventFill, EventOrder, PositionSnapshot
from app.models.data import DataView
from app.services.strategy.event.strategy import OrderService, StrategyContext
from app.models.event import PortfolioView






class EventBacktestEngine:
    """策略在盘前基于截至前一收盘的数据决策，当日开盘按卖后买成交。"""

    required_fields = frozenset({"open", "high", "low", "close"})

    def __init__(self, panels: dict[str, pd.DataFrame], config: EventBacktestConfig | None = None) -> None:
        missing = self.required_fields - panels.keys()
        if missing:
            raise ValueError(f"事件回测缺少行情字段: {sorted(missing)}")
        self.panels = {name: frame.sort_index() for name, frame in panels.items()}
        self.config = config or EventBacktestConfig()
        self.dates = self.panels["close"].index
        self.symbols = list(self.panels["close"].columns)
        if self.dates.empty:
            raise ValueError("事件回测没有可用交易日")

    def run(self, strategy) -> EventBacktestResult:
        ledger = _Ledger(cash=self.config.initial_capital)
        data = DataView(self.panels)
        orders = OrderService()
        context = StrategyContext(data, orders, PortfolioView(ledger))
        strategy.initialize(context)
        all_orders: list[EventOrder] = []
        fills: list[EventFill] = []
        events: list[dict[str, object]] = []
        snapshots: list[PositionSnapshot] = []
        equity: list[float] = []

        for index, date in enumerate(self.dates):
            timestamp = pd.Timestamp(date)
            ledger.begin_session()
            as_of = self.dates[index - 1] if index else None
            data.set_as_of(as_of)
            context.current_dt = timestamp.to_pydatetime()
            orders.set_current_dt(context.current_dt)
            events.append({"type": "SESSION_OPEN", "timestamp": context.current_dt})

            for callback in context.schedule.due(timestamp, self.dates):
                callback(context)
                events.append({"type": "SCHEDULED_CALLBACK", "timestamp": context.current_dt, "callback": callback.__name__})

            batch = list(orders.pending)
            orders.pending.clear()
            all_orders.extend(batch)
            for order in self._sort_orders(batch, ledger, timestamp):
                fill = self._execute(order, ledger, timestamp)
                if fill is None:
                    events.append({"type": "ORDER_REJECTED", "timestamp": context.current_dt, "order_id": order.order_id, "reason_code": order.reason_code})
                else:
                    fills.append(fill)
                    events.append({"type": "FILL", "timestamp": context.current_dt, "order_id": order.order_id})

            close_prices = self.panels["close"].loc[date]
            total_value = ledger.cash + sum(ledger.positions.get(symbol, 0) * float(close_prices[symbol]) for symbol in self.symbols if pd.notna(close_prices[symbol]))
            equity.append(total_value)
            snapshots.append(PositionSnapshot(context.current_dt, ledger.cash, dict(ledger.positions), dict(ledger.sellable), total_value))
            events.append({"type": "SESSION_CLOSE", "timestamp": context.current_dt})

        return EventBacktestResult(
            equity_curve=pd.Series(equity, index=self.dates, name="equity"),
            orders=all_orders,
            fills=fills,
            position_snapshots=snapshots,
            events=events,
            assumptions={"frequency": "1d", "execution": "same_session_open_after_before_open", "data_visibility": "previous_close"},
        )

    def _sort_orders(self, orders: list[EventOrder], ledger: _Ledger, date: pd.Timestamp) -> list[EventOrder]:
        return sorted(orders, key=lambda order: 0 if self._resolved_quantity(order, ledger, date) < 0 else 1)

    def _execute(self, order: EventOrder, ledger: _Ledger, date: pd.Timestamp) -> EventFill | None:
        quantity = self._resolved_quantity(order, ledger, date)
        if quantity == 0:
            order.status, order.reason_code = "rejected", "NO_POSITION"
            return None
        side = "buy" if quantity > 0 else "sell"
        quantity = abs(quantity)
        price = self._price(order.symbol, date)
        if price is None:
            order.status, order.reason_code = "rejected", "NO_PRICE"
            return None
        reason = self._reject_reason(order.symbol, side, quantity, price, ledger, date)
        if reason is not None:
            order.status, order.reason_code = "rejected", reason
            return None
        value = quantity * price
        commission = max(value * self.config.commission_rate, self.config.min_commission)
        stamp_tax = value * self.config.stamp_tax_rate if side == "sell" else 0.0
        if side == "buy":
            current_quantity = ledger.positions.get(order.symbol, 0)
            current_cost = ledger.average_cost.get(order.symbol, 0.0)
            ledger.cash -= value + commission
            ledger.positions[order.symbol] = current_quantity + quantity
            ledger.average_cost[order.symbol] = (
                (current_quantity * current_cost + quantity * price)
                / ledger.positions[order.symbol]
            )
            ledger.bought_today[order.symbol] = ledger.bought_today.get(order.symbol, 0) + quantity
        else:
            ledger.cash += value - commission - stamp_tax
            ledger.positions[order.symbol] -= quantity
            ledger.sellable[order.symbol] -= quantity
            if ledger.positions[order.symbol] == 0:
                ledger.average_cost.pop(order.symbol, None)
        order.status, order.side = "filled", side
        return EventFill(order.order_id, order.symbol, side, quantity, price, date.to_pydatetime(), commission, stamp_tax)

    def _resolved_quantity(self, order: EventOrder, ledger: _Ledger, date: pd.Timestamp) -> int:
        current = ledger.positions.get(order.symbol, 0)
        if order.quantity is not None:
            return order.quantity - current
        price = self._price(order.symbol, date)
        if price is None:
            return 0
        desired = int(order.target_value / price / self.config.lot_size) * self.config.lot_size
        return desired - current

    def _price(self, symbol: str, date: pd.Timestamp) -> float | None:
        if symbol not in self.symbols:
            return None
        value = self.panels["open"].at[date, symbol]
        return float(value) if pd.notna(value) and value > 0 else None

    def _reject_reason(self, symbol: str, side: str, quantity: int, price: float, ledger: _Ledger, date: pd.Timestamp) -> str | None:
        # 当前 iFinD release 只提供 ``up_and_down_status``。停牌字段暂不
        # 参与成交判断，缺失时按放行处理；涨跌停从原始状态文本解析。
        if side == "buy" and self._status_matches(
            date, symbol, r"涨停|limit.?up|up.?limit"
        ):
            return "LIMIT_UP"
        if side == "sell" and self._status_matches(
            date, symbol, r"跌停|limit.?down|down.?limit"
        ):
            return "LIMIT_DOWN"
        if side == "buy":
            if quantity % self.config.lot_size:
                return "LOT_SIZE"
            value = quantity * price
            cost = value + max(value * self.config.commission_rate, self.config.min_commission)
            return "INSUFFICIENT_CASH" if cost > ledger.cash + 1e-9 else None
        return "T_PLUS_ONE" if quantity > ledger.sellable.get(symbol, 0) else None

    def _status_matches(self, date: pd.Timestamp, symbol: str, pattern: str) -> bool:
        frame = self.panels.get("up_and_down_status")
        if frame is None or symbol not in frame.columns or date not in frame.index:
            return False
        value = frame.at[date, symbol]
        if pd.isna(value):
            return False
        text = str(value).strip()
        if re.search(
            r"(?:非|未|not\s*)(?:涨跌停|涨停|跌停|limit.?up|up.?limit|limit.?down|down.?limit)",
            text,
            flags=re.IGNORECASE,
        ):
            return False
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
