"""结构化因子组合策略：因子函数 + 信号公式 -> 目标权重。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from app.services.data.calendar import PandasCalendar
from app.services.data.calendar import ICalendar
from app.services.strategy.vectorized.interfaces import IStrategy
from app.models.strategy import BacktestSignals
from app.services.factor.base import FactorLibrary
from app.models.data import Panel
from app.services.factor.tool import normalize, rank, winsorize, zscore


def factor(method: Callable) -> Callable:
    """标记一个可在 ``@signal`` 中复用的因子方法。"""
    method._svquant_factor = True
    return method


def signal(method: Callable) -> Callable:
    """标记策略唯一的综合选股信号方法。"""
    method._svquant_signal = True
    return method


@dataclass(frozen=True)
class Universe:
    """策略声明的股票池元数据；实际数据由 API 的 ``universe`` 参数解析。"""

    code: str
    exclude_st: bool = False
    exclude_suspended: bool = False

    @classmethod
    def index(
        cls, code: str, *, exclude_st: bool = False, exclude_suspended: bool = False,
    ) -> "Universe":
        return cls(code, exclude_st, exclude_suspended)


@dataclass(frozen=True)
class TopN:
    n: int

    def __post_init__(self) -> None:
        if self.n < 1:
            raise ValueError("TopN 的 n 必须大于 0")


class EqualWeight:
    """入选标的等权。"""


@dataclass(frozen=True)
class EveryNTradingDays:
    n: int

    def __post_init__(self) -> None:
        if self.n < 1:
            raise ValueError("EveryNTradingDays 的 n 必须大于 0")


class FactorPortfolioStrategy(FactorLibrary, IStrategy):
    """声明式多因子组合策略的基类。

    子类用 ``@factor`` 定义因子函数，用唯一 ``@signal`` 返回综合分数，并通过
    ``selector``、``weighting``、``rebalance`` 描述组合构建规则。
    """

    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    def __init__(self, calendar: Optional[ICalendar] = None) -> None:
        self._calendar = calendar or PandasCalendar()

    def _signal_method(self) -> Callable:
        methods = []
        for cls in type(self).__mro__:
            for method in cls.__dict__.values():
                if callable(method) and getattr(method, "_svquant_signal", False):
                    methods.append(method.__get__(self, type(self)))
        if len(methods) != 1:
            raise ValueError("策略必须且只能定义一个使用 @signal 标记的方法")
        return methods[0]

    @staticmethod
    def rank(values: pd.DataFrame) -> pd.DataFrame:
        """按交易日进行横截面百分位排名。"""
        return rank(values)

    @staticmethod
    def zscore(values: pd.DataFrame) -> pd.DataFrame:
        """按交易日横截面标准化；常数行返回 0。"""
        return zscore(values)

    @staticmethod
    def winsorize(values: pd.DataFrame, lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
        """按交易日横截面去极值。"""
        return winsorize(values, lower, upper)

    @staticmethod
    def normalize(values: pd.DataFrame) -> pd.DataFrame:
        """按交易日将绝对值和归一化为 1；全零行保持 0。"""
        return normalize(values)

    def generate_signals(self, panel: Optional[Panel] = None) -> BacktestSignals:
        if panel is None:
            raise ValueError("FactorPortfolioStrategy 需要市场 Panel")
        self._panel = panel
        score = self._signal_method()()
        if not isinstance(score, pd.DataFrame):
            raise TypeError("@signal 方法必须返回 pandas.DataFrame（日期×标的分数）")

        close = self.close.reindex(index=score.index, columns=score.columns)
        score = score.reindex(index=close.index, columns=close.columns)
        ranks = score.rank(axis=1, ascending=False, method="first")
        selected = (ranks <= self.selector.n) & score.notna()
        count = selected.sum(axis=1).replace(0, pd.NA)
        target = selected.div(count, axis=0).fillna(0.0)
        mask = self._calendar.rebalance_mask(target.index, self.rebalance.n)
        return BacktestSignals(target_weights=target.where(mask, float("nan")), close=close)
