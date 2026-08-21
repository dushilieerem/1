"""``BacktestResult`` - 回测结果。

承载向量化回测的净值、收益、持仓与调仓日志。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional

import pandas as pd

def returns_from_equity(equity_curve: pd.Series) -> pd.Series:
    """由净值曲线推导逐期收益率（共用：BacktestResult.returns 与指标层）。"""
    if equity_curve is None or equity_curve.empty:
        return pd.Series(dtype=float)
    return equity_curve.pct_change().dropna()


def rebalance_logs_from_targets(target_weights: pd.DataFrame) -> pd.DataFrame:
    """由目标权重生成调仓日志，仅保留实际发生权重变化的标的。"""
    columns = ["symbol", "side", "previous_weight", "target_weight", "weight_change"]
    if target_weights is None or target_weights.empty:
        return pd.DataFrame(columns=columns)

    effective = target_weights.ffill().fillna(0.0)
    previous = effective.shift(1).fillna(0.0)
    changes = effective - previous
    rows = []
    for date, row in changes.iterrows():
        for symbol, change in row[row.ne(0.0)].items():
            rows.append({
                "date": date,
                "symbol": str(symbol),
                "side": "buy" if change > 0 else "sell",
                "previous_weight": float(previous.at[date, symbol]),
                "target_weight": float(effective.at[date, symbol]),
                "weight_change": float(change),
            })
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).set_index("date")


@dataclass
class BacktestResult:
    """回测结果（仅原始数据，不含任何指标）。

    ``portfolio`` 为兼容旧结果结构保留；向量化适配器
    （``NativeEngine``）不填该字段，置 ``None``，
    直接填 ``returns`` / ``positions``。``returns`` 未显式给时由 ``equity_curve`` 派生。
    """

    portfolio: Optional[Any] = None
    orders: List[Any] = field(default_factory=list)
    fills: List[Any] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    timestamps: List[datetime] = field(default_factory=list)
    #: 逐期收益率（适配器路径显式填；事件路径由 ``equity_curve`` 派生）
    returns: Optional[pd.Series] = None
    #: 持仓权重 ``日期×标的``（适配器路径填；事件路径为 ``None``）
    positions: Optional[pd.DataFrame] = None
    #: 调仓日志（仅含发生权重变化的买入、卖出或减仓目标）
    rebalance_logs: Optional[pd.DataFrame] = None

    def __post_init__(self) -> None:
        if self.returns is None:
            self.returns = returns_from_equity(self.equity_curve)
