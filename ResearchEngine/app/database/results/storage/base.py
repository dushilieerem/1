"""``ResultStorage`` - 存储后端抽象。

依据 ``ResearchEngine/docs/03-功能文档/FEAT-002-研究引擎/04-class-design.md`` ResultManager 节：

    属性：
      name: str                       -- "csv" | "sqlite" | "clickhouse"

    方法：
      write(result: ResultManager)
      read(path: str) -> ResultManager

具体实现：``CSVStorage`` / ``SQLiteStorage`` / ``ClickHouseStorage``。
"""

from __future__ import annotations

import io
import json
from abc import ABC, abstractmethod
from typing import Dict

import pandas as pd


def _factor_values_frame(fv) -> "pd.DataFrame":
    """把因子值规整为 DataFrame（Series -> 单列 DataFrame）。"""
    if isinstance(fv, pd.Series):
        return fv.to_frame("factor_value")
    return fv


class ResultStorage(ABC):
    """结果存储后端抽象。"""

    #: 后端名称
    name: str = "base"

    @abstractmethod
    def write(self, result, path: str) -> None:
        """保存结果到 ``path``。"""

    @abstractmethod
    def read(self, path: str):
        """从 ``path`` 读取并重建 :class:`ResultManager`。"""

    # -- 各后端共享的序列化/反序列化 --
    @staticmethod
    def _artifacts(result) -> Dict[str, str]:
        """把 equity_curve / factor_values / positions 序列化为 JSON 字符串。"""
        arts: Dict[str, str] = {}
        if result.equity_curve is not None:
            arts["equity_curve"] = result.equity_curve.to_json()
        if result.factor_values is not None:
            arts["factor_values"] = _factor_values_frame(result.factor_values).to_json()
        if result.positions is not None:
            arts["positions"] = result.positions.to_json()
        return arts

    @staticmethod
    def _apply_artifacts(result, artifacts: Dict[str, str]) -> None:
        """把 JSON 工件反序列化后填回 result（日期索引恢复）。"""
        if "equity_curve" in artifacts:
            s = pd.read_json(io.StringIO(artifacts["equity_curve"]), typ="series")
            s.index = pd.to_datetime(s.index)
            result.equity_curve = s
        if "factor_values" in artifacts:
            df = pd.read_json(io.StringIO(artifacts["factor_values"]))
            df.index = pd.to_datetime(df.index)
            result.factor_values = df
        if "positions" in artifacts:
            df = pd.read_json(io.StringIO(artifacts["positions"]))
            df.index = pd.to_datetime(df.index)
            result.positions = df
