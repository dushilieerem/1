"""``Position`` / ``Portfolio`` - 持仓与组合。

依据 ``docs/04-类设计.md`` BacktestEngine 节：

    Portfolio
      属性：
        cash: float
        positions: Dict[str, Position]
        total_value: float
        initial_capital: float
      方法：
        update(fill: Fill)
        market_value() -> float
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from quantcore.backtest.order import Fill


@dataclass
class Position:
    """单个标的的持仓。"""

    symbol: str
    quantity: float = 0.0
    #: 持仓均价
    avg_price: float = 0.0

    def market_value(self, price: float) -> float:
        """按给定价格计算的市值。"""
        return self.quantity * price


class Portfolio:
    """组合：现金 + 多头持仓。"""

    def __init__(self, initial_capital: float = 1_000_000.0) -> None:
        self.initial_capital: float = float(initial_capital)
        self.cash: float = float(initial_capital)
        self.positions: Dict[str, Position] = {}
        #: 最近一次盯市价格 symbol -> price，用于 market_value/total_value
        self._prices: Dict[str, float] = {}

    # -- 持仓查询 --
    def get_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def update_prices(self, prices: Dict[str, float]) -> None:
        """更新最新盯市价格。"""
        self._prices.update(prices)

    def market_value(self) -> float:
        """持仓市值（按最近盯市价格）。"""
        total = 0.0
        for symbol, pos in self.positions.items():
            if pos.quantity == 0:
                continue
            price = self._prices.get(symbol, pos.avg_price)
            total += pos.market_value(price)
        return total

    @property
    def total_value(self) -> float:
        """总权益 = 现金 + 持仓市值。"""
        return self.cash + self.market_value()

    # -- 成交更新 --
    def update(self, fill: Fill) -> None:
        """根据成交回报更新现金与持仓。

        买入：现金减少 ``成交额 + 手续费 + 滑点成本``；
        卖出：现金增加 ``成交额 - 手续费 - 滑点成本``。
        """
        trade_value = fill.fill_price * fill.fill_quantity
        cost = fill.commission + fill.slippage
        pos = self.get_position(fill.symbol)

        if fill.direction == 1:  # 买入
            self.cash -= trade_value + cost
            new_qty = pos.quantity + fill.fill_quantity
            if new_qty != 0:
                pos.avg_price = (
                    (pos.avg_price * pos.quantity + fill.fill_price * fill.fill_quantity)
                    / new_qty
                )
            pos.quantity = new_qty
        else:  # 卖出
            self.cash += trade_value - cost
            new_qty = pos.quantity - fill.fill_quantity
            pos.quantity = new_qty
            if abs(new_qty) < 1e-9:
                pos.quantity = 0.0

        # 更新该标的最新价格
        self._prices[fill.symbol] = fill.fill_price

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Portfolio cash={self.cash:.2f} "
            f"market_value={self.market_value():.2f} "
            f"total={self.total_value:.2f} "
            f"positions={len(self.positions)}>"
        )
