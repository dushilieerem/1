"""``FactorEngine`` - 面板因子计算引擎（VectorEngine 模型）。

依据 ``docs/04-类设计.md`` FactorEngine 节与 ``docs/04-engine-design.md §2``：

    属性：
      factors: Dict[str, BaseFactor]

    方法：
      register(factor: BaseFactor)
      compute(factor_name, data_provider, universe, start, end) -> pd.DataFrame
      compute_all(...) -> Dict[str, pd.DataFrame]

运行流程（**面板模式，一次算完，不逐只循环**）：

    ① factor = self.factors[factor_name]
    ② panels = data_provider.get_panels(start, end)   # {field: 日期×标的 宽表}
    ③ 按 universe 过滤列
    ④ factor.compute(Panel(panels))                    # 一次向量化
    ⑤ 返回 日期×标的 因子宽表

**关键原则**：Research 只写 ``factor.compute(data)``，不关心后端与引擎代码。
本引擎不计算 IC 等指标（IC 由 MetricEngine 统一负责）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import pandas as pd

from quantcore.data._util import Universe, resolve_universe
from quantcore.factor.backend import ComputeBackend, get_backend
from quantcore.factor.base import BaseFactor, Panel


def _normalize_factor_output(factor: BaseFactor, values) -> pd.DataFrame:
    """把 compute 的返回值规整为 ``日期×标的`` 宽表 DataFrame。"""
    if isinstance(values, pd.Series):
        values = values.to_frame(name=factor.name)
    values = pd.DataFrame(values)
    values.index.name = "date"
    return values


class FactorEngine:
    """面板因子计算引擎。"""

    def __init__(self, backend: ComputeBackend | str = "python") -> None:
        self.factors: Dict[str, BaseFactor] = {}
        if isinstance(backend, str):
            backend = get_backend(backend)
        self.backend: ComputeBackend = backend

    def register(self, factor: BaseFactor) -> None:
        """注册因子。"""
        if not isinstance(factor, BaseFactor):
            raise TypeError(
                f"只能注册 BaseFactor 子类，得到 {type(factor).__name__}"
            )
        self.factors[factor.name] = factor

    def _panels_for(
        self, data_provider, universe: Universe,
        start: Optional[str], end: Optional[str],
        fields: Optional[Sequence[str]],
    ) -> Panel:
        panels = data_provider.get_panels(start, end, fields)
        # 按 universe 过滤列（懒执行：仅因子访问到的字段才真正读盘+过滤）
        symbols = resolve_universe(data_provider, universe)
        return Panel(panels, symbols=symbols)

    def compute_panel(self, factor_name: str, panel: Panel) -> pd.DataFrame:
        """在已构建好的 ``Panel`` 上计算单个因子，返回 ``日期×标的`` 宽表。

        供调用方复用已取回的面板，避免重复 ``get_panels`` 取数。
        """
        if factor_name not in self.factors:
            raise KeyError(
                f"未注册因子 {factor_name!r}，已注册: {list(self.factors)}"
            )
        return _normalize_factor_output(
            self.factors[factor_name], self.backend.execute(
                self.factors[factor_name].compute, panel
            )
        )

    def compute(
        self,
        factor_name: str,
        data_provider,
        universe: Universe,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """计算单个因子在 universe 上的值，返回 ``日期×标的`` 宽表。"""
        if factor_name not in self.factors:
            raise KeyError(
                f"未注册因子 {factor_name!r}，已注册: {list(self.factors)}"
            )
        panel = self._panels_for(data_provider, universe, start, end, fields)
        return self.compute_panel(factor_name, panel)

    def compute_all(
        self,
        data_provider,
        universe: Universe,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """计算所有已注册因子，返回 ``{因子名: 宽表}``。面板只取一次复用。"""
        panel = self._panels_for(data_provider, universe, start, end, fields)
        return {
            name: _normalize_factor_output(
                factor, self.backend.execute(factor.compute, panel)
            )
            for name, factor in self.factors.items()
        }
