"""适配层信号与配置。

向量化回测的核心数据契约：策略产出「目标权重」宽表（日期×标的），后端引擎
（Native / VectorBT）据此模拟组合、产出净值/收益/持仓。

这与 ResearchEngine 既有的 :func:`researchengine.portfolio.build_factor_portfolio`
内部 ``target_np`` 完全一致--本模块是把「自研向量化回测」提炼成可插拔后端的第一步。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class BacktestSignals:
    """策略产出的向量化信号。

    Attributes
    ----------
    target_weights : pandas.DataFrame
        目标持仓权重 ``日期×标的``。``NaN`` 表示「无目标/不持有」（供 ffill 持有至下一调仓日），
        其余为该日期望权重（多头正、空头负）。**这是两个后端共享的主契约。**
    close : pandas.DataFrame
        对应的收盘价宽表 ``日期×标的``，已与 ``target_weights`` 对齐索引/列。引擎据此算收益率。
    entries, exits : Optional[pandas.DataFrame]
        可选的布尔进/出场信号（供部分 vectorbt 路径使用；默认不用，目标权重即足）。
    """

    target_weights: pd.DataFrame
    close: pd.DataFrame
    entries: Optional[pd.DataFrame] = None
    exits: Optional[pd.DataFrame] = None

    def __post_init__(self) -> None:
        # 与 build_factor_portfolio 的对齐逻辑一致：以 target_weights 为准对齐 close
        if self.target_weights.shape != self.close.shape or (
            not self.target_weights.index.equals(self.close.index)
            or not self.target_weights.columns.equals(self.close.columns)
        ):
            self.close = self.close.reindex(
                index=self.target_weights.index, columns=self.target_weights.columns
            )


@dataclass
class BacktestConfig:
    """回测配置（后端无关）。

    成本默认 0，与 ``build_factor_portfolio`` 现状（不扣成本）逐位一致；显式给
    ``commission_rate`` / ``slippage_rate`` 时两个后端都计入；``stamp_tax`` 仅由
    Native 后端在卖出时计入。

    Notes
    -----
    - ``min_commission``（每笔最低手续费）：Native 支持；VectorBT 原生不支持，按比例近似（已知 fidelity 差异）。
    - 净值口径：Native 保留 ``1.0 + cumsum``（固定本金）；VectorBT 的 ``pf.value()`` 是全额权益，
      引擎内归一化为 ``value / value[0]`` 与之对齐。
    """

    #: 后端名：``"native"`` | ``"vectorbt"``
    engine: str = "native"
    #: 初始资金（仅 VectorBT 透传给 ``init_cash``；Native 固定本金口径不用，但记录以备扩展）
    initial_capital: float = 1_000_000.0
    #: 手续费率（按成交额）
    commission_rate: float = 0.0
    #: 每笔最低手续费（Native 支持；VectorBT 近似/忽略）
    min_commission: float = 0.0
    #: 滑点率（按成交额）
    slippage_rate: float = 0.0
    #: 印花税率（按卖出成交额；仅 Native 支持）
    stamp_tax: float = 0.0
    #: 频率字符串，vectorbt 年化用（日线默认 ``"1D"``）
    freq: str = "1D"
    #: 年化周期数（日线 252）
    periods_per_year: int = 252
    #: vectorbt：全标的合成一个组合、共享现金
    group_by: bool = True
    #: 后端私有参数透传
    extra: dict = field(default_factory=dict)
