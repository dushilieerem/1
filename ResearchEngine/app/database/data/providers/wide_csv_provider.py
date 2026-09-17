"""``WideCSVProvider`` - 读取 Wind/Choice 导出的宽表面板 CSV。

典型格式（如 ``price.CSV``）：

- 第 1 列为日期；其余列为标的代码（如 ``600000.SH``）。
- 表头共 3 行：第 1 行=代码、第 2 行=名称、第 3 行=字段（如 ``收盘价(元)``）。
- 每只标的有多个字段列（开/高/低/收/成交值），pandas 读取重复代码时会自动加
  ``.1``/``.2`` 后缀--这些不是重复，是同代码的不同字段。
- 编码常为 GBK。

本 provider 一次读入整张表，按字段拆成 ``{field: DataFrame[日期×标的]}`` 缓存，
供面板因子向量化计算。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from app.utils.data import filter_by_date
from app.database.data.interface import IDataProvider

#: 标准字段（volume/market_cap 等可选字段按数据是否存在而定）
_STD_FIELDS = ("open", "high", "low", "close", "volume", "market_cap")


def _map_field(field_str: object) -> Optional[str]:
    """把中文字段名映射到标准字段，基于关键字子串匹配（兼容 (元)/(股) 等后缀）。"""
    s = str(field_str)
    # 市值类先判（更具体）
    if "流通市值" in s or "流通" in s:
        return "float_cap"
    if "市值" in s or "总市" in s:
        return "market_cap"
    if "开" in s:
        return "open"
    if "高" in s:
        return "high"
    if "低" in s:
        return "low"
    if "收" in s:
        return "close"
    if "成交" in s or "量" in s or "额" in s:
        return "volume"
    return None


class WideCSVProvider(IDataProvider):
    """读取宽表面板 CSV（多字段、3 行表头、GBK）。"""

    name = "wide_csv"

    def __init__(self, path: str | Path, encoding: str = "gbk") -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"宽表 CSV 不存在: {self.path}")
        self.encoding = encoding
        #: 缓存的面板 {field: DataFrame[日期×标的]}
        self._panels: Optional[dict] = None

    # ---------------- 一次性加载并按字段拆面板 ----------------
    def _load(self) -> "dict[str, pd.DataFrame]":
        if self._panels is not None:
            return self._panels

        # header=[0,1,2] 读取 3 行表头，首列作日期索引
        raw = pd.read_csv(
            self.path, encoding=self.encoding, header=[0, 1, 2], index_col=0
        )
        raw.index = pd.to_datetime(raw.index, errors="coerce")
        raw = raw[raw.index.notna()].sort_index()

        codes = raw.columns.get_level_values(0)
        field_vals = raw.columns.get_level_values(2)

        # 按标准字段分桶
        panels: "dict[str, pd.DataFrame]" = {}
        for std in _STD_FIELDS:
            mask = [_map_field(v) == std for v in field_vals]
            sub = raw.loc[:, mask]
            if sub.empty:
                continue
            sub.columns = sub.columns.get_level_values(0)
            # 同 (代码, 字段) 理论唯一；保险去重
            sub = sub.loc[:, ~sub.columns.duplicated()]
            panels[std] = sub

        if not panels:
            raise ValueError(
                f"未能从 {self.path} 解析出任何 OHLCV 字段，请检查表头第 3 行字段名。"
            )
        self._panels = panels
        return panels

    # ---------------- 面板接口（直接返回缓存，零拷贝）----------------
    def get_panels(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> "dict[str, pd.DataFrame]":
        panels = self._load()
        # 未指定 fields 时返回全部已解析字段
        fields = list(fields) if fields else list(panels.keys())
        result: "dict[str, pd.DataFrame]" = {}
        for f in fields:
            if f not in panels:
                continue
            result[f] = filter_by_date(panels[f], start, end)
        return result

    # ---------------- 逐只接口（从面板切出单只 OHLCV，向后兼容）----------------
    def get_bars(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        panels = self._load()
        fields = list(fields) if fields else list(panels.keys())
        cols: "dict[str, pd.Series]" = {}
        for f in fields:
            if f in panels and symbol in panels[f].columns:
                cols[f] = panels[f][symbol]
        if not cols:
            return pd.DataFrame()
        df = pd.DataFrame(cols)
        df.index.name = "date"
        return filter_by_date(df, start, end)

    def get_universe(self, date: Optional[str] = None) -> List[str]:
        panels = self._load()
        # 以 close 字段为准（若有），否则取任一字段
        key = "close" if "close" in panels else next(iter(panels))
        return list(panels[key].columns)

    def get_symbols(self) -> List[str]:
        return self.get_universe()
