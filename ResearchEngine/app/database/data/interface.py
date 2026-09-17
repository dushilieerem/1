"""``IDataProvider`` - 数据源抽象接口。

依据 ``docs/99-历史归档/FEAT-001-QuantCore基础能力/04-class-design.md`` DataEngine 节：

    属性：
      name: str                  -- 数据源名称（如 "csv", "wind"）

    方法：
      get_bars(symbol, start, end, fields) -> DataFrame
      get_universe(date) -> List[str]
      get_symbols() -> List[str]

**关键原则**：Research 永远不知道数据来自哪里，只通过 ``IDataProvider`` 接口获取数据。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

import pandas as pd


class IDataProvider(ABC):
    """数据源统一接口。

    所有具体数据源（CSV / ClickHouse / AkShare / Wind / Parquet）都实现该接口，
    由 :class:`app.services.data.engine.DataEngine` 持有并委托调用，从而对上层屏蔽来源差异。
    """

    #: 数据源名称，如 ``"csv"``、``"wind"``
    name: str = "base"

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """读取单个标的的 OHLCV 行情。

        Parameters
        ----------
        symbol:
            标的代码。
        start, end:
            起止日期（含），``None`` 表示不限制。支持 ``str``（如 ``"2020-01-01"``）或 ``datetime``。
        fields:
            需要返回的字段，``None`` 表示返回全部。标准字段为
            ``["open", "high", "low", "close", "volume"]``。

        Returns
        -------
        pandas.DataFrame
            ``DatetimeIndex``，列为所请求字段。
        """

    @abstractmethod
    def get_universe(self, date: Optional[str] = None) -> List[str]:
        """获取指定日期的股票池（universe）。``date=None`` 表示返回默认全集。"""

    @abstractmethod
    def get_symbols(self) -> List[str]:
        """返回该数据源已知的全部标的代码。"""

    # ---------------- 面板接口（向量化的首选路径）----------------
    def get_panels(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> "dict[str, pd.DataFrame]":
        """读取多字段的宽表面板 ``{field: DataFrame[日期×标的]}``。

        这是面板因子计算（VectorEngine）的首选数据入口：一次返回整张
        ``日期×标的`` 宽表，因子可一次性向量化计算，无需逐只循环。

        默认实现基于 :meth:`get_bars` 逐只拼装（适用于任何逐只 provider）；
        宽表 provider（如 :class:`WideCSVProvider`）应重写为直接返回缓存面板以提速。
        """
        fields = list(fields) if fields else ["open", "high", "low", "close", "volume"]
        per_field: "dict[str, dict]" = {f: {} for f in fields}
        for symbol in self.get_symbols():
            bars = self.get_bars(symbol, start, end, fields)
            if bars.empty:
                continue
            for f in fields:
                if f in bars.columns:
                    per_field[f][symbol] = bars[f]
        return {f: pd.DataFrame(d) for f, d in per_field.items()}

    def get_index(
        self,
        name: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取指数行情；不支持的数据源保持默认实现。"""
        raise NotImplementedError(f"{self.name} 不支持读取指数行情")
