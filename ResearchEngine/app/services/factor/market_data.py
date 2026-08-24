"""面向 Web 图表的只读日线行情查询。"""

from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from app.quantcore import DataEngine, FieldParquetProvider
from app.core.exceptions import (
    MarketDataError,
    MarketDataNotFoundError,
    MarketDataValidationError,
)
from app.services.factor.runner import _resolve_data_dir


@dataclass(frozen=True)
class MarketDateRange:
    start: str
    end: str


@dataclass(frozen=True)
class MarketBar:
    date: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class MarketDailyBars:
    symbol: str
    name: str
    bars: tuple[MarketBar, ...]
    date_range: MarketDateRange


@dataclass(frozen=True)
class MarketSymbol:
    symbol: str
    name: str


@dataclass(frozen=True)
class MarketSymbols:
    symbols: tuple[MarketSymbol, ...]
    unmapped_count: int


@dataclass(frozen=True)
class MarketIndex:
    code: str
    name: str


@dataclass(frozen=True)
class MarketIndices:
    indices: tuple[MarketIndex, ...]


@dataclass(frozen=True)
class MarketIndexConstituents:
    index: MarketIndex
    constituents: tuple[MarketSymbol, ...]
    unmapped_count: int


_DATA_ENGINES: dict[Path, DataEngine] = {}
_DISPLAY_DATA_ENGINES: dict[Path, DataEngine] = {}
_STOCK_NAMES: dict[Path, dict[str, str]] = {}
_OHLC_FIELDS = ("open", "high", "low", "close")
_INDEXES = {
    "CSI300": MarketIndex(code="000300.SH", name="沪深300"),
    "CSI500": MarketIndex(code="000905.SH", name="中证500"),
}


def _market_symbol(symbol: str) -> str:
    """将面板使用的六位代码转换为对外的交易所代码。"""
    if not symbol.isdigit() or len(symbol) != 6:
        return symbol
    if symbol.startswith("92"):
        return f"{symbol}.BJ"
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "2", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return symbol


def _panel_symbol(symbol: str) -> str:
    """将 API 代码转换为当前行情面板使用的六位代码。"""
    for suffix in (".SH", ".SZ", ".BJ"):
        if symbol.upper().endswith(suffix):
            return symbol[:-len(suffix)]
    return symbol


def _get_data_engine() -> DataEngine:
    """按数据目录复用 Provider，以复用其字段级 Parquet 缓存。"""
    data_dir = Path(_resolve_data_dir(None)).resolve()
    if data_dir not in _DATA_ENGINES:
        _DATA_ENGINES[data_dir] = DataEngine(FieldParquetProvider(data_dir))
    return _DATA_ENGINES[data_dir]


def _get_display_data_engine() -> DataEngine:
    """读取 Web 展示专用未复权行情，与研究/回测用行情物理隔离。"""
    data_dir = Path(_resolve_data_dir(None)).resolve()
    current_dir = data_dir / "current" if (data_dir / "current").is_dir() else data_dir
    display_file = current_dir / "display" / "unadjusted_price.parquet"
    if display_file not in _DISPLAY_DATA_ENGINES:
        _DISPLAY_DATA_ENGINES[display_file] = DataEngine(
            FieldParquetProvider(display_file)
        )
    return _DISPLAY_DATA_ENGINES[display_file]


def _get_stock_names() -> dict[str, str]:
    """读取已发布证券主数据中的 ``代码 -> 名称`` 映射。"""
    data_dir = Path(_resolve_data_dir(None)).resolve()
    if data_dir in _STOCK_NAMES:
        return _STOCK_NAMES[data_dir]

    current_dir = data_dir / "current"
    candidates = (
        current_dir / "metadata" / "stock_info.parquet",
        data_dir / "metadata" / "stock_info.parquet",
        data_dir / "stock_info.parquet",
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise FileNotFoundError("缺少证券主数据 stock_info.parquet")

    stock_info = pd.read_parquet(path)
    code_column = next(
        (column for column in ("symbol", "code", "ts_code") if column in stock_info), None
    )
    if code_column is None and stock_info.index.name in {"symbol", "code", "ts_code"}:
        stock_info = stock_info.reset_index()
        code_column = stock_info.columns[0]
    if code_column is None or "name" not in stock_info:
        raise KeyError("证券主数据必须包含代码列（symbol/code/ts_code）和 name 列")

    names = {
        _panel_symbol(str(row[code_column])): str(row["name"])
        for _, row in stock_info[[code_column, "name"]].dropna().iterrows()
        if str(row["name"]).strip()
    }
    _STOCK_NAMES[data_dir] = names
    return names


def get_daily_bars(
    symbol: str, start: date | None = None, end: date | None = None
) -> MarketDailyBars:
    """读取一个标的的完整日线 OHLC，返回领域值对象。"""
    if start is not None and end is not None and start > end:
        raise MarketDataValidationError("start 不能晚于 end")
    panel_symbol = _panel_symbol(symbol)

    try:
        bars = _get_display_data_engine().get_bars(
            panel_symbol,
            str(start) if start else None,
            str(end) if end else None,
            _OHLC_FIELDS,
        )
    except (FileNotFoundError, NotADirectoryError, KeyError) as exc:
        raise MarketDataError(f"日线数据不可用: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 读取失败不可伪造行情
        raise MarketDataError(f"日线数据读取失败: {exc}") from exc

    if bars.empty:
        raise MarketDataNotFoundError(f"未找到 {symbol} 的完整日线数据")

    missing = set(_OHLC_FIELDS).difference(bars.columns)
    if missing:
        raise MarketDataError(f"日线数据缺少字段: {sorted(missing)}")
    bars = bars.loc[:, list(_OHLC_FIELDS)].dropna().sort_index()
    if bars.empty:
        raise MarketDataNotFoundError(f"未找到 {symbol} 的完整日线数据")

    points = [
        MarketBar(
            date=pd.Timestamp(index).date().isoformat(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
        )
        for index, row in bars.iterrows()
    ]
    try:
        name = _get_stock_names()[panel_symbol]
    except (FileNotFoundError, KeyError) as exc:
        raise MarketDataError(f"证券名称数据不可用: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 读取失败不可伪造证券名称
        raise MarketDataError(f"证券名称读取失败: {exc}") from exc

    return MarketDailyBars(
        symbol=_market_symbol(panel_symbol),
        name=name,
        bars=tuple(points),
        date_range=MarketDateRange(start=points[0].date, end=points[-1].date),
    )


def get_symbols() -> MarketSymbols:
    """返回当前已发布市场数据中的全部可查询股票代码。"""
    try:
        symbols = _get_display_data_engine().get_symbols()
        names = _get_stock_names()
    except (FileNotFoundError, NotADirectoryError, KeyError) as exc:
        raise MarketDataError(f"股票代码数据不可用: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 读取失败不可伪造股票列表
        raise MarketDataError(f"股票代码读取失败: {exc}") from exc

    available_symbols = sorted(set(symbols).intersection(names))
    return MarketSymbols(
        symbols=tuple(
            MarketSymbol(symbol=_market_symbol(symbol), name=names[symbol])
            for symbol in available_symbols
        ),
        unmapped_count=len(set(symbols).difference(names)),
    )


def _resolve_index(code: str) -> str:
    """将对外股指代码解析为 QuantCore 的内置基准标识。"""
    normalized = code.upper()
    for identifier, index in _INDEXES.items():
        if normalized in {identifier, index.code}:
            return identifier
    raise MarketDataNotFoundError(f"未找到股指代码 {code}")


def get_indices() -> MarketIndices:
    """返回当前已发布市场数据中可用的全部内置股指。"""
    available = []
    try:
        engine = _get_data_engine()
        for identifier, index in _INDEXES.items():
            try:
                if not engine.get_index(identifier).empty:
                    available.append(index)
            except FileNotFoundError:
                continue
    except (NotADirectoryError, KeyError) as exc:
        raise MarketDataError(f"股指数据不可用: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 读取失败不可伪造股指列表
        raise MarketDataError(f"股指数据读取失败: {exc}") from exc

    if not available:
        raise MarketDataError("没有可用的股指数据")
    return MarketIndices(indices=tuple(sorted(available, key=lambda index: index.code)))


def get_index_constituents(code: str) -> MarketIndexConstituents:
    """返回指定内置股指在当前发布版本中的最新一期成分股。"""
    identifier = _resolve_index(code)
    try:
        constituents = _get_data_engine().get_universe(identifier)
        names = _get_stock_names()
    except (FileNotFoundError, NotADirectoryError, KeyError) as exc:
        raise MarketDataError(f"股指成分数据不可用: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 读取失败不可伪造成分股
        raise MarketDataError(f"股指成分数据读取失败: {exc}") from exc

    available_symbols = sorted(set(constituents).intersection(names))
    return MarketIndexConstituents(
        index=_INDEXES[identifier],
        constituents=tuple(
            MarketSymbol(symbol=_market_symbol(symbol), name=names[symbol])
            for symbol in available_symbols
        ),
        unmapped_count=len(set(constituents).difference(names)),
    )


__all__ = [
    "MarketBar",
    "MarketDateRange",
    "MarketDailyBars",
    "MarketIndex",
    "MarketIndexConstituents",
    "MarketIndices",
    "MarketSymbol",
    "MarketSymbols",
    "get_daily_bars",
    "get_index_constituents",
    "get_indices",
    "get_symbols",
]
