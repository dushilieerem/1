"""``ResultManager`` - 结果管理（只保存，不计算）。

依据 ``docs/04-features/FEAT-002-research-engine/04-class-design.md`` ResultManager 节：

    属性：
      metrics: Dict[str, float]
      factor_values: pd.Series
      equity_curve: pd.Series
      storage: ResultStorage

    方法：
      save(path: str)
      load(path: str)
      get_metric(name: str) -> float
      all_metrics() -> Dict[str, float]
      set_metric(name: str, value: float)

**关键原则**：ResultManager 不计算任何指标，结果来自 QuantCore 的 MetricEngine。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

import pandas as pd

if TYPE_CHECKING:  # 仅类型提示用，避免运行时循环导入
    from researchengine.result.storage.base import ResultStorage


class ResultManager:
    """实验结果管理器。"""

    def __init__(
        self,
        metrics: Optional[Dict[str, float]] = None,
        factor_values: Optional[pd.Series] = None,
        equity_curve: Optional[pd.Series] = None,
        positions: Optional[pd.DataFrame] = None,
        storage: "Optional[ResultStorage]" = None,
        meta: Optional[Dict] = None,
    ) -> None:
        self.metrics: Dict[str, float] = dict(metrics) if metrics else {}
        self.factor_values = factor_values
        self.equity_curve = equity_curve
        self.positions = positions
        self.storage = storage
        self.meta: Dict = dict(meta) if meta else {}

    # -- 指标读写 --
    def set_metric(self, name: str, value: float) -> None:
        """记录指标值。"""
        self.metrics[name] = float(value)

    def get_metric(self, name: str, default: float = float("nan")) -> float:
        """获取指标值。"""
        return self.metrics.get(name, default)

    def all_metrics(self) -> Dict[str, float]:
        """返回全部指标。"""
        return dict(self.metrics)

    # -- 持久化 --
    def save(self, path: str) -> None:
        """保存结果（委托给 storage）。"""
        if self.storage is None:
            raise RuntimeError("未设置 storage，无法保存。请先指定 ResultStorage。")
        self.storage.write(self, path)

    def load(self, path: str) -> "ResultManager":
        """从路径加载结果（委托给 storage，返回新实例）。"""
        if self.storage is None:
            raise RuntimeError("未设置 storage，无法加载。请先指定 ResultStorage。")
        return self.storage.read(path)

    def summary(self) -> str:
        """生成可读的指标摘要。"""
        if not self.metrics:
            return "(无指标)"
        lines = ["指标摘要:"]
        for name in sorted(self.metrics):
            lines.append(f"  {name:16s}: {self.metrics[name]:+.4f}")
        return "\n".join(lines)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ResultManager metrics={len(self.metrics)} "
            f"equity={'Y' if self.equity_curve is not None else 'N'} "
            f"factor={'Y' if self.factor_values is not None else 'N'}>"
        )
