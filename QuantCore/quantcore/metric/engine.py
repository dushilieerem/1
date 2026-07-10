"""``MetricEngine`` - 指标统一入口。

依据 ``docs/04-类设计.md`` MetricEngine 节与 ``docs/05-运行流程图.md`` 第 5 节：

    属性：
      metrics: Dict[str, BaseMetric]

    方法：
      register(metric: BaseMetric)
      calculate(metric_names: List[str], data) -> Dict[str, float]
      calculate_all(data) -> Dict[str, float]

运行流程：遍历请求的指标名 -> 取出指标 -> ``metric.calculate(data)`` -> 收集结果。

**关键原则**：Backtest 不算 Sharpe，Factor 不算 IC，全部集中在此。
Research 只调用 ``metric.calculate(...)``。
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from quantcore.metric.base import BaseMetric
from quantcore.metric.context import MetricContext
from quantcore.metric.metrics.standard import default_metrics


class MetricEngine:
    """所有指标的统一入口。"""

    def __init__(self, register_defaults: bool = True) -> None:
        self.metrics: Dict[str, BaseMetric] = {}
        if register_defaults:
            for name, metric in default_metrics().items():
                self.metrics[name] = metric

    def register(self, metric: BaseMetric) -> None:
        """注册指标。"""
        if not isinstance(metric, BaseMetric):
            raise TypeError(
                f"只能注册 BaseMetric 子类，得到 {type(metric).__name__}"
            )
        self.metrics[metric.name] = metric

    def calculate(
        self,
        metric_names: Iterable[str],
        ctx: MetricContext,
    ) -> Dict[str, float]:
        """计算指定指标。"""
        result: Dict[str, float] = {}
        for name in metric_names:
            if name not in self.metrics:
                raise KeyError(f"未注册指标 {name!r}，已注册: {list(self.metrics)}")
            result[name] = float(self.metrics[name].calculate(ctx))
        return result

    def calculate_all(self, ctx: MetricContext) -> Dict[str, float]:
        """计算全部已注册指标。"""
        return self.calculate(list(self.metrics), ctx)
