"""``MetricContext`` - 指标计算的输入上下文。

``docs/04-类设计.md`` 中 ``BaseMetric.calculate(data)`` 单参签名无法表达 IC 这类
需要「因子值 + 远期收益」双序列的指标。因此用一个上下文对象把所有可能的输入聚合
在一起，每个指标按需取用。这是对文档签名的工程化补充，语义不变：

    MetricEngine.calculate(metric_names, data)   # data 即 MetricContext

字段全部可选，指标自行决定取哪些。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class MetricContext:
    """指标输入上下文。

    Attributes
    ----------
    equity_curve : pd.Series, optional
        净值曲线（按日期索引）。用于年化收益、Calmar、最大回撤。
    returns : pd.Series, optional
        逐期收益率序列。用于 Sharpe、Sortino、波动率、胜率。
    factor_values : pd.DataFrame, optional
        因子值 ``日期×标的`` 宽表。用于 IC、RankIC。
    forward_returns : pd.DataFrame, optional
        远期收益 ``日期×标的`` 宽表，与 factor_values 对齐。用于 IC、RankIC。
    positions : pd.DataFrame, optional
        持仓权重 ``日期×标的`` 宽表。用于换手率。
    periods_per_year : int
        年化周期数（日线默认 252）。
    """

    equity_curve: Optional[pd.Series] = None
    returns: Optional[pd.Series] = None
    factor_values: Optional[pd.DataFrame] = None
    forward_returns: Optional[pd.DataFrame] = None
    positions: Optional[pd.DataFrame] = None
    periods_per_year: int = 252
