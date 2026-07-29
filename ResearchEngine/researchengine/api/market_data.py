"""面向 Web 图表的只读日线行情查询。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import HTTPException

from quantcore import DataEngine, FieldParquetProvider
from researchengine.api.runner import _resolve_data_dir
from researchengine.api.schemas import (
    DailyBar,
    DailyBarsResponse,
    DateRange,
    StockInfo,
    SymbolListResponse,
)


_DATA_ENGINES: dict[Path, DataEngine] = {}
_STOCK_NAMES: dict[Path, dict[str, str]] = {}
_OHLC_FIELDS = ("open", "high", "low", "close")


def _market_symbol(symbol: str) -> str:
    """将面板使用的六位代码转换为对外的交易所代码。"""
    if not symbol.isdigit() or len(symbol) != 6:
        return symbol
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
) -> DailyBarsResponse:
    """读取一个标的的完整日线 OHLC，并转换为 Web 友好的 JSON 契约。"""
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="start 不能晚于 end")
    panel_symbol = _panel_symbol(symbol)

    try:
        bars = _get_data_engine().get_bars(
            panel_symbol,
            str(start) if start else None,
            str(end) if end else None,
            _OHLC_FIELDS,
        )
    except (FileNotFoundError, NotADirectoryError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=f"日线数据不可用: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 读取失败不可伪造行情
        raise HTTPException(status_code=503, detail=f"日线数据读取失败: {exc}") from exc

    if bars.empty:
        raise HTTPException(status_code=404, detail=f"未找到 {symbol} 的完整日线数据")

    missing = set(_OHLC_FIELDS).difference(bars.columns)
    if missing:
        raise HTTPException(status_code=503, detail=f"日线数据缺少字段: {sorted(missing)}")
    bars = bars.loc[:, list(_OHLC_FIELDS)].dropna().sort_index()
    if bars.empty:
        raise HTTPException(status_code=404, detail=f"未找到 {symbol} 的完整日线数据")

    points = [
        DailyBar(
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
        raise HTTPException(status_code=503, detail=f"证券名称数据不可用: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 读取失败不可伪造证券名称
        raise HTTPException(status_code=503, detail=f"证券名称读取失败: {exc}") from exc

    return DailyBarsResponse(
        symbol=_market_symbol(panel_symbol),
        name=name,
        bars=points,
        date_range=DateRange(start=points[0].date, end=points[-1].date),
    )


def get_symbols() -> SymbolListResponse:
    """返回当前已发布市场数据中的全部可查询股票代码。"""
    try:
        symbols = _get_data_engine().get_symbols()
        names = _get_stock_names()
    except (FileNotFoundError, NotADirectoryError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=f"股票代码数据不可用: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 读取失败不可伪造股票列表
        raise HTTPException(status_code=503, detail=f"股票代码读取失败: {exc}") from exc

    available_symbols = sorted(set(symbols).intersection(names))
    return SymbolListResponse(
        symbols=[StockInfo(symbol=_market_symbol(symbol), name=names[symbol]) for symbol in available_symbols],
        unmapped_count=len(set(symbols).difference(names)),
    )
