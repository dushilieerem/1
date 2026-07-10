"""``BacktestResult`` - 回测结果。

依据 ``docs/04-类设计.md`` BacktestEngine 节：

    属性：
      portfolio: Portfolio
      orders: List[Order]
      fills: List[Fill]
      equity_curve: pd.Series
      timestamps: List[datetime]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List

import pandas as pd

from quantcore.backtest.order import Fill, Order
from quantcore.backtest.portfolio import Portfolio


def returns_from_equity(equity_curve: pd.Series) -> pd.Series:
    """由净值曲线推导逐期收益率（共用：BacktestResult.returns 与指标层）。"""
    if equity_curve is None or equity_curve.empty:
        return pd.Series(dtype=float)
    return equity_curve.pct_change().dropna()


@dataclass
class BacktestResult:
    """回测结果（仅原始数据，不含任何指标）。"""

    portfolio: Portfolio
    orders: List[Order] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    timestamps: List[datetime] = field(default_factory=list)

    @property
    def returns(self) -> pd.Series:
        """净值曲线的逐期收益率。"""
        return returns_from_equity(self.equity_curve)
