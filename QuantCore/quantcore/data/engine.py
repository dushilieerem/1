"""``DataEngine`` - 统一数据读取引擎。

依据 ``docs/04-features/FEAT-001-quantcore-core/04-class-design.md`` DataEngine 节：

    属性：
      provider: IDataProvider    -- 统一通过接口调用，不关心具体来源

    方法：
      set_provider(provider: IDataProvider)
      get_bars(symbol, start, end, fields) -> DataFrame
      get_universe(date) -> List[str]

DataEngine 永远只持有 ``IDataProvider``，数据源对 Research 完全透明。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import pandas as pd

from quantcore.data.interface import IDataProvider


class DataEngine:
    """统一数据读取入口。

    上层（ResearchEngine）只与本类交互，不接触任何具体数据源实现。
    切换数据源只需调用 :meth:`set_provider`。
    """

    def __init__(self, provider: Optional[IDataProvider] = None) -> None:
        self.provider: Optional[IDataProvider] = provider

    def set_provider(self, provider: IDataProvider) -> None:
        """切换数据源。"""
        self.provider = provider

    def _require_provider(self) -> IDataProvider:
        if self.provider is None:
            raise RuntimeError(
                "DataEngine 尚未设置数据源，请先调用 set_provider(...)。"
            )
        return self.provider

    def get_bars(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """读取单个标的行情，委托给当前 provider。"""
        return self._require_provider().get_bars(symbol, start, end, fields)

    def get_universe(self, date: Optional[str] = None) -> List[str]:
        """获取股票池，委托给当前 provider。"""
        return self._require_provider().get_universe(date)

    def get_universe_at(self, name: str, as_of: str | pd.Timestamp) -> List[str]:
        """获取指定时点的命名股票池；不支持历史快照时兼容旧 provider。"""
        provider = self._require_provider()
        resolver = getattr(provider, "get_universe_at", None)
        if callable(resolver):
            return resolver(name, as_of)
        return provider.get_universe(name)

    def get_symbols(self) -> List[str]:
        """获取全部已知标的，委托给当前 provider。"""
        return self._require_provider().get_symbols()

    def get_panels(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> "dict[str, pd.DataFrame]":
        """获取多字段宽表面板，委托给当前 provider。"""
        return self._require_provider().get_panels(start, end, fields)

    def get_index(
        self,
        name: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取指数行情，委托给当前 provider。"""
        return self._require_provider().get_index(name, start, end)
