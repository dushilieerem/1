"""``FieldParquetProvider`` - 读取「一个字段一个 parquet」的目录。

每个 ``{field}.parquet`` 是一张 ``日期×标的`` 宽表（行=日期，列=标的代码），
多个字段文件组成完整面板，正好对应 :meth:`get_panels` 返回的
``{field: DataFrame[日期×标的]}``。

典型数据源（如某行情导出）目录：

::

    parquet/
    ├── close.parquet       # 收盘价
    ├── open.parquet        # 开盘价
    ├── high.parquet / low.parquet / volume.parquet / amount.parquet
    ├── total_mv.parquet   # 总市值
    ├── pe_ttm.parquet / pb.parquet / ps_ttm.parquet
    └── ...

**懒加载**：仅在字段被访问时才读盘并缓存，跑一个只用 close 的因子不会把
18 个文件全读进来。``pd.read_parquet`` 在新版 pyarrow 下可能因列索引存成
``categorical`` 报错，这里用 ``replace_schema_metadata({})`` 绕过。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from quantcore.data._util import filter_by_date, require_optional
from quantcore.data.interface import IDataProvider

#: MarketData 字段（文件名即字段名，不做改名）：
#:   价格: open / high / low / close
#:   成交: volume / amount / turnover
#:   股本市值: total_shares / float_shares / total_mv / float_mv
#:   估值: pe_ttm / pb / ps_ttm
#:   布尔: is_st / limit_up
#: 非面板文件（如 stock_info），跳过
_SKIP = {"stock_info", "test"}
_UNIVERSE_FILES = {
    "CSI300": "CSI300_constituents.parquet",
    "CSI500": "CSI500_constituents.parquet",
    "CSI1000": "CSI1000_constituents.parquet",
    "SSE50": "SSE50_constituents.parquet",
}
_INDEX_FILES = {
    "CSI300": "index_000300.parquet",
    "CSI500": "index_000905.parquet",
    "CSI1000": "index_000852.parquet",
    "SSE50": "index_000016.parquet",
}


class _LazyPanels:
    """按字段懒加载的面板映射。``__getitem__`` 时才读盘并缓存。"""

    def __init__(self, provider, fields, start, end):
        self._provider = provider
        self._fields = fields
        self._start = start
        self._end = end
        self._cache: dict = {}

    def __contains__(self, name: str) -> bool:
        return name in self._fields

    def __getitem__(self, name: str) -> pd.DataFrame:
        if name not in self._cache:
            df = self._provider._read_field(name)
            self._cache[name] = filter_by_date(df, self._start, self._end)
        return self._cache[name]

    def get(self, name: str, default=None):
        return self[name] if name in self._fields else default

    def __iter__(self):
        return iter(self._fields)

    def keys(self):
        return list(self._fields)

    def __len__(self):
        return len(self._fields)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LazyPanels fields={self._fields}>"


class FieldParquetProvider(IDataProvider):
    """读取「一个字段一个 parquet」目录的数据源。"""

    name = "field_parquet"

    def __init__(self, data_dir: str | Path) -> None:
        require_optional("pyarrow", "FieldParquetProvider 需要 pyarrow")
        self.data_dir = Path(data_dir)
        if not self.data_dir.is_dir():
            raise NotADirectoryError(f"parquet 目录不存在: {self.data_dir}")
        #: 文件名 -> 标准字段名 的映射（仅本目录实际存在的）
        self._field_files: dict = self._scan_fields()
        #: 字段数据缓存 {field: DataFrame}
        self._cache: dict = {}

    def _scan_fields(self) -> dict:
        result = {}
        for p in self.data_dir.glob("*.parquet"):
            if p.stem in _SKIP:
                continue
            result[p.stem] = p   # 文件名即字段名
        return result

    # -- 读单个字段（绕过 categorical 元数据）--
    def _read_field(self, field: str) -> pd.DataFrame:
        if field in self._cache:
            return self._cache[field]
        import pyarrow.parquet as pq

        path = self._field_files[field]
        table = pq.read_table(path).replace_schema_metadata({})
        df = table.to_pandas()
        # 'datetime' 列做日期索引（无则取首列）
        idx_col = "datetime" if "datetime" in df.columns else df.columns[0]
        df = df.set_index(idx_col)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        self._cache[field] = df
        return df

    # -- 面板接口（懒加载）--
    def get_panels(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> "_LazyPanels":
        available = list(self._field_files)
        if fields is not None:
            missing = [f for f in fields if f not in available]
            if missing:
                raise KeyError(f"缺少字段文件: {missing}，可用: {available}")
            available = list(fields)
        return _LazyPanels(self, available, start, end)

    def get_index(
        self,
        name: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取基准指数日线，返回以日期为索引的 OHLCV 表。"""
        try:
            filename = _INDEX_FILES[name.upper()]
        except KeyError as exc:
            raise KeyError(f"不支持的指数 {name!r}，可用: {list(_INDEX_FILES)}") from exc
        path = self.data_dir / "benchmark" / filename
        if not path.is_file():
            raise FileNotFoundError(f"缺少指数行情文件: {path}")
        frame = pd.read_parquet(path)
        prefix = filename.removeprefix("index_").removesuffix(".parquet")
        frame = frame.rename(columns={
            f"{prefix}_{field}": field
            for field in ("open", "high", "low", "close", "volume")
        })
        frame.index = pd.to_datetime(frame.index)
        return filter_by_date(frame.sort_index(), start, end)

    # -- 逐只接口（从面板切出单只，向后兼容）--
    def get_bars(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        fields = list(fields) if fields else list(self._field_files)
        cols: dict = {}
        for f in fields:
            if f in self._field_files:
                df = self._read_field(f)
                if symbol in df.columns:
                    cols[f] = df[symbol]
        if not cols:
            return pd.DataFrame()
        out = pd.DataFrame(cols)
        out.index.name = "date"
        return filter_by_date(out, start, end)

    def get_universe(self, date: Optional[str] = None) -> List[str]:
        """返回股票池成分；池名取最新一期成分，日期查询仍回退全市场。

        ``IDataProvider`` 的参数名为 ``date``，但上层 ``resolve_universe`` 也用它
        传入 ``CSI500`` 等池名。字段 parquet 数据目录中的指数成分文件按日期保存，
        此处取最新一期有效成分；逐日调入调出需要由上层持仓掩码处理，不能仅靠列筛选
        正确表达。
        """
        pool = str(date).upper() if date is not None else None
        if pool in _UNIVERSE_FILES:
            path = self.data_dir / "benchmark" / _UNIVERSE_FILES[pool]
            if not path.exists():
                raise FileNotFoundError(f"股票池 {pool} 缺少成分文件: {path}")
            frame = pd.read_parquet(path)
            if frame.empty:
                return []
            latest = frame.iloc[-1]
            return [
                str(symbol).split(".", 1)[0]
                for symbol, included in latest.items()
                if included == 1
            ]

        # 读 close 字段 schema 取列名（不读数据），无 close 则取首个
        import pyarrow.parquet as pq

        field = "close" if "close" in self._field_files else next(
            iter(self._field_files)
        )
        names = pq.read_schema(self._field_files[field]).names
        return [n for n in names if n != "datetime"]

    def get_symbols(self) -> List[str]:
        return self.get_universe()
