"""计算结果数据；不读取文件、不管理存储或计算指标。"""

from __future__ import annotations

from dataclasses import dataclass, field
import pandas as pd


@dataclass(eq=False)
class ResultData:
    metrics: dict[str, float] = field(default_factory=dict)
    factor_values: pd.Series | pd.DataFrame | None = None
    equity_curve: pd.Series | None = None
    returns: pd.Series | None = None
    positions: pd.DataFrame | None = None
    rebalance_logs: pd.DataFrame | None = None
    target_weights: pd.DataFrame | None = None
    forward_returns: pd.DataFrame | None = None
    meta: dict = field(default_factory=dict)
