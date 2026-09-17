"""适配层接口（领域词汇）。

六个领域接口 + :class:`IBacktestEngine` 适配器契约，对应 ``docs/03-功能文档/FEAT-003-回测适配层/03-technical-design.md``：

================  =====================================================  ====================
接口              职责                                                   在 Native / 事件路径中的角色
================  =====================================================  ====================
``IStrategy``     策略产出向量化信号（目标权重）                          NativeEngine 的主契约
``IDataFeed``     行情面板来源（= 现有 DataEngine / IDataProvider）        共享输入
``ICalendar``     交易日 / 调仓日历                                       策略与事件引擎用
``IPortfolio``    组合状态契约                                            事件引擎可插拔件；向量化后端内化
``IExecution``    撮合 / 成本契约                                          事件引擎可插拔件；向量化后端内化
``IMetrics``     指标计算（= 现有 MetricEngine）                          共享输出消费方
================  =====================================================  ====================

Native 向量化后端遵守顶层 :meth:`IBacktestEngine.run` 契约，内化
portfolio / execution / calendar；事件驱动自研引擎（未来 EventEngine）才把后三者当可插拔件。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, Sequence, runtime_checkable

import pandas as pd

from app.models.strategy import BacktestConfig, BacktestSignals
from app.models.data import Panel


class IStrategy(ABC):
    """策略接口（向量化信号模式）。

    策略把市场面板转化为「目标权重」宽表，由 NativeEngine 据此模拟。事件驱动
    ``on_bar`` 式策略留待 EventEngine，不在本适配器。
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




class IDataFeed(ABC):
    """行情面板来源（向量化首选路径）。

    现有 :class:`app.services.data.engine.DataEngine` / ``IDataProvider.get_panels`` 已满足该契约；
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

    向量化后端不直接使用；日频 EventEngine 使用独立的现金账本实现。
    """

    @abstractmethod
    def update_prices(self, prices: "dict[str, float]") -> None:
        """更新最新盯市价格。"""

    @abstractmethod
    def update(self, fill: object) -> None:
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

    向量化后端内化执行；事件引擎按市场规则和执行模型实现。
    """

    @abstractmethod
    def match(self, order: object, bar, timestamp: "object | None" = None) -> List[object]:
        """对单个订单撮合，返回成交回报列表。"""


@runtime_checkable
class IMetrics(Protocol):
    """指标计算契约（= 现有 :class:`app.services.metric.engine.MetricEngine`）。

    用 :class:`typing.Protocol` 避免强改 MetricEngine 继承体系；MetricEngine 已结构性满足。
    """

    def calculate_all(self, ctx) -> "dict[str, float]": ...

    def register(self, metric) -> None: ...


class IBacktestEngine(ABC):
    """回测后端适配器契约。

    NativeEngine 实现该接口：吃策略信号 + 配置，产出
    :class:`app.models.backtest.BacktestResult`。
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

from app.services.data.calendar import ICalendar
