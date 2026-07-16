"""``MatchingEngine`` - 撮合引擎。

依据 ``docs/04-features/FEAT-001-quantcore-core/04-class-design.md`` BacktestEngine 节与 ``docs/04-features/FEAT-001-quantcore-core/05-runtime-flow.md`` 第 4.1 节：

    方法：
      match(order: Order, bars: DataFrame) -> List[Fill]

撮合规则：

- 市价单：以当前 bar 的 close 成交；
- 限价单：比较 order.price 与 bar 价格区间
    - 买单：bar low <= order.price <= bar high 时以 order.price 成交；
    - 卖单：bar low <= order.price <= bar high 时以 order.price 成交；
    - 未触达 -> 不成交（挂单 / 由调用方决定取消）。
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd

from quantcore.backtest.order import Fill, Order


class MatchingEngine:
    """订单撮合引擎。"""

    def match(self, order: Order, bar, timestamp: datetime | None = None) -> List[Fill]:
        """对单个订单撮合。

        Parameters
        ----------
        order:
            待成交订单。
        bar:
            当前 bar。可为：

            - ``pd.Series``，含 ``open/high/low/close``（单标的单 bar）；或
            - ``pd.Series``，索引为标的代码、值为 close（截面 close）；或
            - 标量 close 价格。
        timestamp:
            成交时间，默认取 ``bar.name``（时间索引）。
        """
        close, high, low = self._extract_prices(bar, order.symbol)
        if timestamp is None:
            timestamp = getattr(bar, "name", None) or datetime.now()

        if order.order_type == "market":
            fill_price = close
        elif order.order_type == "limit":
            fill_price = self._try_limit(order, high, low, close)
            if fill_price is None:
                # 未触达限价，不成交
                return []
        else:  # pragma: no cover
            raise ValueError(f"未知 order_type: {order.order_type!r}")

        if fill_price is None or fill_price != fill_price:  # NaN 检查
            return []

        fill = Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            direction=order.direction,
            fill_price=float(fill_price),
            fill_quantity=float(order.quantity),
            fill_time=timestamp,
        )
        order.status = "filled"
        return [fill]

    @staticmethod
    def _extract_prices(bar, symbol: str):
        """从 bar 中提取 (close, high, low)。缺失字段以 close 近似。"""
        if isinstance(bar, pd.Series):
            if "close" in bar.index:
                close = float(bar["close"])
                high = float(bar.get("high", close))
                low = float(bar.get("low", close))
                return close, high, low
            # 截面 close：索引为标的代码
            if symbol in bar.index:
                close = float(bar[symbol])
                return close, close, close
            # 标量 Series
            close = float(bar.iloc[0])
            return close, close, close
        # 标量
        close = float(bar)
        return close, close, close

    @staticmethod
    def _try_limit(order: Order, high: float, low: float, close: float):
        """限价单触达判定，返回成交价或 None。"""
        price = order.price
        if price is None:
            return None
        if low <= price <= high:
            return price
        # 收盘价穿越限价也视为成交（稳健处理）
        if order.direction == 1 and close <= price:
            return price
        if order.direction == -1 and close >= price:
            return price
        return None
