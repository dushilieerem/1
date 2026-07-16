"""适配层接口（领域词汇）。

六个领域接口 + :class:`IBacktestEngine` 适配器契约，对应 ``docs/04-features/FEAT-003-backtest-adapter/03-technical-design.md``：

================  =====================================================  ====================
接口              职责                                                   在两个后端中的角色
================  =====================================================  ====================
``IStrategy``     策略产出向量化信号（目标权重）                          **共享主契约**（两后端都吃）
``IDataFeed``     行情面板来源（= 现有 DataEngine / IDataProvider）        共享输入
``ICalendar``     交易日 / 调仓日历                                       策略与事件引擎用
``IPortfolio``    组合状态契约                                            事件引擎可插拔件；向量化后端内化
``IExecution``    撮合 / 成本契约                                          事件引擎可插拔件；向量化后端内化
``IMetrics``     指标计算（= 现有 MetricEngine）                          共享输出消费方
================  =====================================================  ====================

向量化后端（Native / VectorBT）只遵守顶层 :meth:`IBacktestEngine.run` 契约，内化
portfolio / execution / calendar；事件驱动自研引擎（未来 EventEngine）才把后三者当可插拔件。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, Sequence, runtime_checkable

import pandas as pd

from quantcore.backtest.adapter.signals import BacktestConfig, BacktestSignals
from quantcore.backtest.order import Fill, Order
from quantcore.factor.base import Panel


class IStrategy(ABC):
    """策略接口（向量化信号模式）。

    策略把市场面板转化为「目标权重」宽表，后端引擎据此模拟。这是 vectorbt 与自研引擎
    共同消费的主契约--vectorbt 跑不了 bar 回调，故事件驱动 ``on_bar`` 式策略留待未来
    EventEngine，不在本适配器。
    """

    #: 策略名称
    name: str = "base"

    @abstractmethod
    def generate_signals(self, panel: Optional[Panel] = None) -> BacktestSignals:
        """产出目标权重信号 ``日期×标的``。

        Parameters
        ----------
        panel:
            市场面板（可选）。预计算型策略（如 :class:`FactorQuantileStrategy`）可忽略，
            用构造时传入的因子值/收盘价；从面板现算的策略则取用所需字段。
        """


class ICalendar(ABC):
    """交易日历 / 调仓节奏契约。"""

    @abstractmethod
    def rebalance_mask(self, index: pd.DatetimeIndex, freq: str | int) -> pd.Series:
        """标记每个日期是否为调仓日（布尔序列，首日必为 ``True``）。"""

    @abstractmethod
    def is_trading_day(self, date) -> bool:
        """是否为交易日。"""

    @abstractmethod
    def trading_days(self, start=None, end=None) -> pd.DatetimeIndex:
        """取区间内交易日序列。"""


class IDataFeed(ABC):
    """行情面板来源（向量化首选路径）。

    现有 :class:`quantcore.data.engine.DataEngine` / ``IDataProvider.get_panels`` 已满足该契约；
    本接口是回测向的薄抽象，便于未来换源而不动策略/引擎代码。
    """

    @abstractmethod
    def get_panel(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> "dict[str, pd.DataFrame]":
        """读取多字段宽表面板 ``{field: DataFrame[日期×标的]}``。"""

    @abstractmethod
    def get_universe(self, date: Optional[str] = None) -> List[str]:
        """取股票池。"""


class IPortfolio(ABC):
    """组合状态契约（事件引擎用）。

    现有 :class:`quantcore.backtest.portfolio.Portfolio` 是其参考实现（见
    :mod:`quantcore.backtest.adapter` 的虚拟子类注册）；向量化后端不直接使用，仅在事件驱动
    自研引擎中作为可插拔件。
    """

    @abstractmethod
    def update_prices(self, prices: "dict[str, float]") -> None:
        """更新最新盯市价格。"""

    @abstractmethod
    def update(self, fill: Fill) -> None:
        """根据成交回报更新现金与持仓。"""

    @abstractmethod
    def market_value(self) -> float:
        """持仓市值（按最近盯市价格）。"""

    @property
    @abstractmethod
    def total_value(self) -> float:
        """总权益 = 现金 + 持仓市值。"""


class IExecution(ABC):
    """撮合 / 成本契约（事件引擎用）。

    现有 :class:`quantcore.backtest.matching.MatchingEngine`（配合
    :class:`quantcore.backtest.cost.TransactionCost`）是其参考实现；向量化后端内化、不直接用。
    """

    @abstractmethod
    def match(self, order: Order, bar, timestamp: "object | None" = None) -> List[Fill]:
        """对单个订单撮合，返回成交回报列表。"""


@runtime_checkable
class IMetrics(Protocol):
    """指标计算契约（= 现有 :class:`quantcore.metric.engine.MetricEngine`）。

    用 :class:`typing.Protocol` 避免强改 MetricEngine 继承体系；MetricEngine 已结构性满足。
    """

    def calculate_all(self, ctx) -> "dict[str, float]": ...

    def register(self, metric) -> None: ...


class IBacktestEngine(ABC):
    """回测后端适配器契约。

    两个后端（Native / VectorBT）实现同一接口：吃策略信号 + 配置，产出
    :class:`quantcore.backtest.result.BacktestResult`。**切后端 = 换实现，ResearchEngine 无感。**
    """

    #: 后端名
    name: str = "base"

    @abstractmethod
    def run(
        self,
        signals: BacktestSignals,
        config: BacktestConfig,
    ) -> "BacktestResult":  # noqa: F821  (避免与 result 循环导入)
        """运行回测，返回净值 / 收益 / 持仓等原始数据（不含指标）。"""
