"""``BaseMetric`` - 指标抽象基类。

依据 ``docs/04-类设计.md`` MetricEngine 节：

    属性：
      name: str                  -- 指标名称（如 "sharpe", "annual_return"）

    方法：
      calculate(data) -> float

实现上 ``calculate`` 接收 :class:`quantcore.metric.context.MetricContext`，
各指标按需取用其中的字段（详见 context 模块说明）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from quantcore.metric.context import MetricContext


class BaseMetric(ABC):
    """指标基类。"""

    #: 指标名称
    name: str = "base"

    @abstractmethod
    def calculate(self, ctx: MetricContext) -> float:
        """计算指标值。"""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} name={self.name!r}>"
