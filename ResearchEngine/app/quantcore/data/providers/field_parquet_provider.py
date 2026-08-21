"""``FieldParquetProvider`` - 按逻辑字段读取 Parquet 面板。

目标布局按业务域使用多字段宽表，兼容旧版 ``{field}.parquet`` 单字段文件。
无论磁盘如何分组，:meth:`get_panels` 都返回
``{field: DataFrame[日期×标的]}``。

典型数据源（如某行情导出）目录：

::

    panels/
    ├── market_data.parquet
    ├── daily_basic.parquet
    └── security_status.parquet

**懒加载**：仅在字段被访问时才读对应物理列并缓存，跑一个只用 close 的因子不会把
同文件其他字段读进来。``pd.read_parquet`` 在新版 pyarrow 下可能因列索引存成
``categorical`` 报错，这里用 ``replace_schema_metadata({})`` 绕过。
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import threading
from typing import List, Optional, Sequence

import pandas as pd

from app.quantcore.data._util import filter_by_date, require_optional
from app.quantcore.data.field_cache import FieldFrameCache, get_process_field_cache
from app.quantcore.data.interface import IDataProvider

#: MarketData 字段（文件名即字段名，不做改名）：
#:   价格: open / high / low / close
#:   成交: volume / amount / turnover
#:   股本市值: total_shares / float_shares / total_mv / float_mv
#:   估值: pe_ttm / pb / ps_ttm
#:   布尔: is_st / limit_up
#: 非面板文件（如 stock_info），跳过
_SKIP = {"stock_info", "test"}
_UNIVERSE_FILES = {
    "CSI300": "index_weights_000300.SH.parquet",
    "CSI500": "index_weights_000905.SH.parquet",
}
_INDEX_FILES = {
    "CSI300": "index_price_000300.SH.parquet",
    "CSI500": "index_price_000905.SH.parquet",
}
_ALL_A_NAMES = {"CSI_ALL", "ALL_A", "A_SHARE"}
_DOMAIN_PANEL_FILES = ("market_data.parquet", "daily_basic.parquet", "security_status.parquet")

# ``FieldParquetProvider`` 会在每次初始化时扫描合并宽表的 schema。API 请求通常
# 会创建多个 provider，这个只读元数据扫描不需要重复执行。缓存项带文件指纹，
# 数据版本切换或文件更新后会自动失效；进程重启也会自然清空。
_SCHEMA_CACHE: dict[Path, tuple[int, int, object]] = {}


def _release_signature(data_dir: Path, panels_dir: Path, benchmark_dir: Path) -> str:
    """按已发布数据文件的 stat 信息生成进程内缓存命名空间。"""

    roots = [panels_dir, benchmark_dir, data_dir / "universe"]
    rows: list[tuple[str, int, int]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.parquet")):
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            rows.append((str(path.relative_to(data_dir)), stat.st_size, stat.st_mtime_ns))
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_schema_cached(path: Path):
    """读取 Parquet schema，并按文件大小/mtime 缓存。"""
    resolved = path.resolve()
    stat = resolved.stat()
    cached = _SCHEMA_CACHE.get(resolved)
    fingerprint = (stat.st_size, stat.st_mtime_ns)
    if cached is not None and cached[:2] == fingerprint:
        return cached[2]

    import pyarrow.parquet as pq

    schema = pq.read_schema(resolved)
    _SCHEMA_CACHE[resolved] = (stat.st_size, stat.st_mtime_ns, schema)
    return schema


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

    def get_view(self, name: str, symbols=None) -> pd.DataFrame:
        """返回共享缓存中的日期/股票池字段视图。"""

        symbol_key = None if symbols is None else tuple(str(symbol) for symbol in symbols)
        key = (name, symbol_key)
        if key not in self._cache:
            self._cache[key] = self._provider._get_field_view(
                name,
                self._start,
                self._end,
                symbols,
            )
        return self._cache[key]

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.get_view(name)

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
    """读取按业务域组织的多字段宽表，并兼容旧版单字段目录。"""

    name = "field_parquet"

    def __init__(
        self,
        data_dir: str | Path,
        *,
        cache: FieldFrameCache | None = None,
    ) -> None:
        require_optional("pyarrow", "FieldParquetProvider 需要 pyarrow")
        self.data_dir = Path(data_dir)
        self._combined_files: set[Path] = set()
        self._combined_columns: dict[str, list[tuple[str, str]]] = {}
        self._combined_field_files: dict[str, Path] = {}
        self._combined_index_columns: dict[Path, str] = {}
        if self.data_dir.is_file():
            if self.data_dir.suffix.lower() != ".parquet":
                raise ValueError(f"只支持 parquet 合并面板文件: {self.data_dir}")
            combined_file = self.data_dir
            self._scan_combined_file(combined_file)
            self.data_dir = self.data_dir.parent
        elif not self.data_dir.is_dir():
            raise NotADirectoryError(f"parquet 目录不存在: {self.data_dir}")
        # MarketData 根目录采用 ``current/`` 指向当前已发布数据版本；保留传入
        # 旧版扁平目录及直接传入 current 目录的兼容性。
        current_dir = self.data_dir / "current"
        if current_dir.is_dir():
            self.data_dir = current_dir
        panels_dir = self.data_dir / "panels"
        self._panels_dir = panels_dir if panels_dir.is_dir() else self.data_dir
        if not self._combined_files:
            for filename in _DOMAIN_PANEL_FILES:
                combined_file = self._panels_dir / filename
                if combined_file.is_file():
                    self._scan_combined_file(combined_file)
        benchmark_dir = self.data_dir / "benchmark"
        self._benchmark_dir = benchmark_dir if benchmark_dir.is_dir() else self.data_dir / "benchmark"
        self._all_a_file = self.data_dir / "universe" / "a_share.parquet"
        #: 文件名 -> 标准字段名 的映射（仅本目录实际存在的）
        self._field_files: dict = self._scan_fields()
        self.release_id = _release_signature(
            self.data_dir,
            self._panels_dir,
            self._benchmark_dir,
        )
        self._cache_namespace = f"{self.data_dir.resolve()}:{self.release_id}"
        self._cache = cache or get_process_field_cache()
        self._universe_cache: dict[tuple[str | None, str], list[str]] = {}
        self._universe_lock = threading.RLock()

    def _scan_fields(self) -> dict:
        result = {}
        for p in self._panels_dir.glob("*.parquet"):
            if p.stem in _SKIP or p in self._combined_files:
                continue
            result[p.stem] = p   # 文件名即字段名
        result.update(self._combined_field_files)
        return result

    def _scan_combined_file(self, path: Path) -> None:
        """识别 iFinD 合并宽表中的 ``(证券代码, 字段)`` 列。"""
        schema = _read_schema_cached(path)
        metadata = schema.pandas_metadata or {}
        index_columns = metadata.get("index_columns", [])
        if index_columns and isinstance(index_columns[0], str):
            self._combined_index_columns[path] = index_columns[0]

        found_fields: set[str] = set()
        for column in schema.names:
            try:
                symbol, field = ast.literal_eval(column)
            except (SyntaxError, ValueError, TypeError):
                continue
            if isinstance(symbol, str) and isinstance(field, str):
                existing = self._combined_field_files.get(field)
                if existing is not None and existing != path:
                    raise ValueError(f"逻辑字段 {field!r} 同时存在于 {existing} 和 {path}")
                self._combined_columns.setdefault(field, []).append((column, symbol))
                self._combined_field_files[field] = path
                found_fields.add(field)

        if not found_fields:
            raise ValueError(
                f"合并 parquet 不包含 '(证券代码, 字段)' 两级列: {path}"
            )
        self._combined_files.add(path)

    def _combined_symbol(self, symbol: str) -> str:
        """将六位代码匹配到合并面板中的交易所代码。"""
        available = self._combined_columns.get(
            "close", next(iter(self._combined_columns))
        )
        symbols = [item[1] for item in available]
        if symbol in symbols:
            return symbol
        base = str(symbol).split(".", 1)[0]
        return next((item for item in symbols if item.split(".", 1)[0] == base), symbol)

    @staticmethod
    def _standard_symbol(symbol: str) -> str:
        """将供应商交易所代码归一为平台既有的六位代码。"""
        return str(symbol).split(".", 1)[0]

    # -- 读单个字段（绕过 categorical 元数据）--
    def _read_field(self, field: str) -> pd.DataFrame:
        key = ("field", self._cache_namespace, field)

        def load() -> pd.DataFrame:
            import pyarrow.parquet as pq

            path = self._field_files[field]
            if field in self._combined_columns:
                columns = self._combined_columns[field]
                names = [name for name, _ in columns]
                index_column = self._combined_index_columns.get(path, "date")
                table = pq.read_table(
                    path,
                    columns=[*names, index_column],
                ).replace_schema_metadata({})
                df = table.to_pandas().set_index(index_column)
                df.columns = [self._standard_symbol(symbol) for _, symbol in columns]
                df.index = pd.to_datetime(df.index)
                df.index.name = "datetime"
                return df.sort_index()

            table = pq.read_table(path).replace_schema_metadata({})
            df = table.to_pandas()
            # 新文件通常将日期显式写为 ``datetime`` 列；历史 Pandas Parquet 在移除
            # metadata 后会把索引保留为 ``__index_level_0__`` 列。
            if "datetime" in df.columns:
                idx_col = "datetime"
            elif "__index_level_0__" in df.columns:
                idx_col = "__index_level_0__"
            else:
                idx_col = df.columns[0]
            df = df.set_index(idx_col)
            df.index = pd.to_datetime(df.index)
            df.index.name = "datetime"
            return df.sort_index()

        return self._cache.get_or_load(key, load)

    def _get_field_view(
        self,
        field: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        symbols=None,
    ) -> pd.DataFrame:
        """返回共享的原始字段日期/股票池视图。"""

        symbol_key = None if symbols is None else tuple(str(symbol) for symbol in symbols)
        start_key = None if start is None else str(pd.Timestamp(start))
        end_key = None if end is None else str(pd.Timestamp(end))
        key = (
            "view",
            self._cache_namespace,
            field,
            start_key,
            end_key,
            symbol_key,
        )

        def load() -> pd.DataFrame:
            df = self._read_field(field)
            if start is not None or end is not None:
                df = filter_by_date(df, start, end)
            if symbols is not None:
                requested = pd.Index(symbol_key)
                if not df.columns.equals(requested):
                    df = df.reindex(columns=requested)
            return df

        if start is None and end is None and symbols is None:
            return self._read_field(field)
        return self._cache.get_or_load(key, load)

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
        path = self._benchmark_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"缺少指数行情文件: {path}")
        start_key = None if start is None else str(pd.Timestamp(start))
        end_key = None if end is None else str(pd.Timestamp(end))
        key = ("index", self._cache_namespace, name.upper(), start_key, end_key)

        def load() -> pd.DataFrame:
            frame = pd.read_parquet(path)
            prefix = filename.removeprefix("index_").removesuffix(".parquet")
            frame = frame.rename(columns={
                f"{prefix}_{field}": field
                for field in ("open", "high", "low", "close", "volume")
            })
            frame.index = pd.to_datetime(frame.index)
            return filter_by_date(frame.sort_index(), start, end)

        return self._cache.get_or_load(key, load)

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
                column = self._standard_symbol(symbol) if f in self._combined_columns else symbol
                if column in df.columns:
                    cols[f] = df[column]
        if not cols:
            return pd.DataFrame()
        out = pd.DataFrame(cols)
        out.index.name = "date"
        return filter_by_date(out, start, end)

    def get_universe(self, date: Optional[str] = None) -> List[str]:
        """返回股票池成分；池名取最新一期成分，日期查询仍回退全市场。

        ``IDataProvider`` 的参数名为 ``date``，但上层 ``resolve_universe`` 用它
        传入 ``CSI500`` 等池名。指数权重表同时表达历史成分，此处取最新一行中
        权重非空且大于零的证券；逐日调入调出仍应由上层按同一权重表生成掩码。
        """
        pool = str(date).upper() if date is not None else None
        cache_key = (pool, "latest")
        with self._universe_lock:
            cached = self._universe_cache.get(cache_key)
            if cached is not None:
                return list(cached)
        requested_all_a = pool in _ALL_A_NAMES
        if (requested_all_a or pool is None) and self._all_a_file.is_file():
            frame = pd.read_parquet(self._all_a_file, columns=["thscode"])
            result = [
                self._standard_symbol(symbol)
                for symbol in frame["thscode"].dropna().astype(str)
            ]
            with self._universe_lock:
                self._universe_cache[cache_key] = result
            return list(result)
        if requested_all_a:
            pool = None
        if pool in _UNIVERSE_FILES:
            path = self._benchmark_dir / _UNIVERSE_FILES[pool]
            if not path.exists():
                raise FileNotFoundError(f"股票池 {pool} 缺少指数权重文件: {path}")
            frame = pd.read_parquet(path)
            if frame.empty:
                return []
            latest = frame.iloc[-1]
            symbols = [
                str(symbol) for symbol, weight in latest.items()
                if pd.notna(weight) and float(weight) > 0
            ]
            result = [self._standard_symbol(symbol) for symbol in symbols]
            with self._universe_lock:
                self._universe_cache[cache_key] = result
            return list(result)
        if pool is not None:
            raise KeyError(f"不支持的股票池 {pool!r}，可用: {sorted(_ALL_A_NAMES | set(_UNIVERSE_FILES))}")

        # 读 close 字段 schema 取列名（不读数据），无 close 则取首个
        if self._combined_files:
            field = "close" if "close" in self._combined_columns else next(
                iter(self._combined_columns)
            )
            result = [self._standard_symbol(symbol) for _, symbol in self._combined_columns[field]]
            with self._universe_lock:
                self._universe_cache[cache_key] = result
            return list(result)

        field = "close" if "close" in self._field_files else next(
            iter(self._field_files)
        )
        names = _read_schema_cached(self._field_files[field]).names
        result = [n for n in names if n != "datetime"]
        with self._universe_lock:
            self._universe_cache[cache_key] = result
        return list(result)

    def get_universe_at(self, name: str, as_of: str | pd.Timestamp) -> List[str]:
        """返回 ``as_of`` 当日可知的命名股票池快照。

        权重文件不一定每天都有一行，因此使用不晚于 ``as_of`` 的最近一期，
        绝不向后取未来快照。全 A 股票池是静态列表，日期对其没有影响。
        """
        pool = str(name).upper()
        if pool in _ALL_A_NAMES:
            return self.get_universe(pool)
        if pool not in _UNIVERSE_FILES:
            return self.get_universe(pool)

        cache_key = (pool, str(pd.Timestamp(as_of).normalize()))
        with self._universe_lock:
            cached = self._universe_cache.get(cache_key)
            if cached is not None:
                return list(cached)
        path = self._benchmark_dir / _UNIVERSE_FILES[pool]
        if not path.is_file():
            raise FileNotFoundError(f"股票池 {pool} 缺少指数权重文件: {path}")
        frame = pd.read_parquet(path)
        if frame.empty:
            return []
        frame.index = pd.to_datetime(frame.index)
        frame = frame.sort_index()
        snapshots = frame.loc[frame.index <= pd.Timestamp(as_of)]
        if snapshots.empty:
            raise ValueError(f"股票池 {pool} 在 {pd.Timestamp(as_of).date()} 当日没有可用快照")
        row = snapshots.iloc[-1]
        symbols = [
            str(symbol) for symbol, weight in row.items()
            if pd.notna(weight) and float(weight) > 0
        ]
        result = [self._standard_symbol(symbol) for symbol in symbols]
        with self._universe_lock:
            self._universe_cache[cache_key] = result
        return list(result)

    def get_symbols(self) -> List[str]:
        return self.get_universe()
