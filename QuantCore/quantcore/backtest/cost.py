"""``TransactionCost`` - 手续费与滑点模型。

依据 ``docs/04-类设计.md`` BacktestEngine 节：

    属性：
      commission_rate: float
      min_commission: float
      slippage_rate: float

    方法：
      calculate(order: Order, fill_price: float) -> (commission, slippage)
"""

from __future__ import annotations

from typing import Tuple

from quantcore.backtest.order import Order


class TransactionCost:
    """交易成本模型。"""

    def __init__(
        self,
        commission_rate: float = 0.0003,
        min_commission: float = 5.0,
        slippage_rate: float = 0.001,
    ) -> None:
        self.commission_rate = float(commission_rate)
        self.min_commission = float(min_commission)
        self.slippage_rate = float(slippage_rate)

    def calculate(self, order: Order, fill_price: float) -> Tuple[float, float]:
        """计算手续费与滑点成本（货币金额）。

        Returns
        -------
        (commission, slippage)
            ``commission`` 不低于 ``min_commission``；``slippage`` 为滑点成本金额。
        """
        trade_value = fill_price * order.quantity
        commission = max(trade_value * self.commission_rate, self.min_commission)
        slippage = trade_value * self.slippage_rate
        return float(commission), float(slippage)
