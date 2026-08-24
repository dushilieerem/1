"""使用 AkShare ``stock_value_em`` 历史回填全 A 股日频估值字段。

``stock_value_em`` 直接返回东方财富估值分析历史数据。本脚本保留以下十个
字段，不重新用价格和股本推导市值：

    total_market_cap, notlimited_marketcap_a, total_shares, free_shares_a,
    pe_ttm, pe_lar, pb_mrq, peg_car, pcf_ocf_ttm, ps_ttm

脚本逐证券请求并写入独立 Parquet 缓存，再按日期分块合并为
``(symbol, field)`` 宽面板。合并阶段一次只读取一个证券缓存，内存上限由
``chunk_size × 证券数 × 字段数`` 控制，不会把所有缓存或现有
``MarketData/current/panels/daily_basic.parquet`` 一次加载到内存，也不会覆盖
``current``。

运行示例（在 ``MarketData/DataIngestion`` 目录执行）：

    python -m data_ingestion.akshare.update_float_mv --start-date 2017-01-03 --end-date 2026-08-14

需要先在项目根目录安装可选依赖：

    cd D:\\project\\SVQuant
    pip install -e ".[akshare]"

注意：``stock_value_em`` 没有日期参数，返回该证券可用的估值历史；脚本在
本地筛选日期区间。免费数据源依赖东方财富公开接口，默认串行请求、限速、
重试并保留失败清单；当前 AkShare 实现单次请求最多返回 5000 条记录，极
早上市证券需要通过报告检查历史起点。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "MarketData"
DEFAULT_UNIVERSE_RELATIVE = Path("current") / "universe" / "a_share.parquet"
DEFAULT_CACHE_RELATIVE = Path("sources") / "akshare" / "daily_basic" / "by_symbol"
DEFAULT_OUTPUT_RELATIVE = Path("sources") / "akshare" / "daily_basic"

_CODE_PATTERN = re.compile(r"^(?P<code>\d{6})\.(?P<exchange>SH|SZ|BJ)$", re.IGNORECASE)
_DATE_COLUMNS = ("数据日期", "date", "日期", "datetime")

# 标准字段顺序同时决定缓存列和最终宽表列顺序。
VALUATION_FIELDS = (
    "total_market_cap",
    "notlimited_marketcap_a",
    "total_shares",
    "free_shares_a",
    "pe_ttm",
    "pe_lar",
    "pb_mrq",
    "peg_car",
    "pcf_ocf_ttm",
    "ps_ttm",
)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "total_market_cap": ("TOTAL_MARKET_CAP", "总市值", "total_market_cap"),
    "notlimited_marketcap_a": (
        "NOTLIMITED_MARKETCAP_A",
        "流通市值",
        "notlimited_marketcap_a",
    ),
    "total_shares": ("TOTAL_SHARES", "总股本", "total_shares"),
    "free_shares_a": ("FREE_SHARES_A", "流通股本", "free_shares_a"),
    "pe_ttm": ("PE_TTM", "PE(TTM)", "pe_ttm"),
    "pe_lar": ("PE_LAR", "PE(静)", "pe_lar"),
    "pb_mrq": ("PB_MRQ", "市净率", "pb_mrq"),
    "peg_car": ("PEG_CAR", "PEG值", "peg_car"),
    "pcf_ocf_ttm": ("PCF_OCF_TTM", "市现率", "pcf_ocf_ttm"),
    "ps_ttm": ("PS_TTM", "市销率", "ps_ttm"),
}

FIELD_UNITS = {
    "total_market_cap": "CNY",
    "notlimited_marketcap_a": "CNY",
    "total_shares": "share",
    "free_shares_a": "share",
    "pe_ttm": "multiple",
    "pe_lar": "multiple",
    "pb_mrq": "multiple",
    "peg_car": "multiple",
    "pcf_ocf_ttm": "multiple",
    "ps_ttm": "multiple",
}

ValuationFetcher = Callable[[str], pd.DataFrame]


def normalize_date(value: str | date | pd.Timestamp, label: str) -> pd.Timestamp:
    """将日期标准化为无时区日戳。"""

    try:
        timestamp = pd.Timestamp(value).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}格式无效：{value!r}，应为 YYYY-MM-DD") from exc
    if pd.isna(timestamp):
        raise ValueError(f"{label}不能为空")
    return timestamp


def normalize_date_range(
    start_date: str | date | pd.Timestamp,
    end_date: str | date | pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = normalize_date(start_date, "开始日期")
    end = normalize_date(end_date, "结束日期")
    if start > end:
        raise ValueError(f"开始日期不能晚于结束日期：{start.date()} > {end.date()}")
    return start, end


def api_date(value: pd.Timestamp) -> str:
    return value.strftime("%Y%m%d")


def symbol_to_code(symbol: str) -> str:
    """将 SVQuant 的 ``000001.SZ`` 转成 ``stock_value_em`` 使用的六位代码。"""

    match = _CODE_PATTERN.fullmatch(str(symbol).strip().upper())
    if match is None:
        raise ValueError(f"证券代码格式无效：{symbol!r}")
    return match.group("code")


def load_universe_mapping(path: Path) -> tuple[tuple[str, ...], dict[str, str]]:
    """读取当前 A 股证券池，返回保持原顺序的 symbol 和六位代码映射。"""

    if not path.is_file():
        raise FileNotFoundError(f"A 股证券池不存在：{path}")
    universe = pd.read_parquet(path, columns=["thscode"])
    if "thscode" not in universe.columns:
        raise ValueError(f"证券池缺少 thscode 列：{path}")

    symbols: list[str] = []
    by_code: dict[str, str] = {}
    for raw_symbol in universe["thscode"].tolist():
        symbol = str(raw_symbol).strip().upper()
        match = _CODE_PATTERN.fullmatch(symbol)
        if match is None:
            raise ValueError(f"证券池存在非法证券代码：{raw_symbol!r}")
        code = match.group("code")
        if code in by_code:
            raise ValueError(f"证券池存在重复六位代码：{code}")
        symbols.append(symbol)
        by_code[code] = symbol
    if not symbols:
        raise ValueError(f"证券池为空：{path}")
    return tuple(symbols), by_code


def _find_column(frame: pd.DataFrame, candidates: Sequence[str], label: str) -> str:
    matches = {
        str(column).strip().casefold(): str(column)
        for column in frame.columns
    }
    for candidate in candidates:
        found = matches.get(candidate.casefold())
        if found is not None:
            return found
    raise ValueError(
        f"AkShare 估值历史返回缺少 {label} 列；收到列："
        f"{[str(column) for column in frame.columns]}"
    )


def _numeric(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(text, errors="coerce").astype("float64")


def _empty_valuation() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.Series(dtype="datetime64[ns]"),
            "symbol": pd.Series(dtype="string"),
            **{field: pd.Series(dtype="float64") for field in VALUATION_FIELDS},
        }
    )


def normalize_valuation(
    history: pd.DataFrame,
    symbol: str,
    start_date: str | date | pd.Timestamp,
    end_date: str | date | pd.Timestamp,
) -> pd.DataFrame:
    """标准化 ``stock_value_em`` 返回值并保留十个直接指标。"""

    start, end = normalize_date_range(start_date, end_date)
    if not isinstance(history, pd.DataFrame):
        raise TypeError("AkShare 估值历史必须是 pandas.DataFrame")
    if history.empty:
        return _empty_valuation()

    date_column = _find_column(history, _DATE_COLUMNS, "日期")
    selected = pd.DataFrame(
        {"date": pd.to_datetime(history[date_column], errors="coerce").dt.normalize()}
    )
    for field in VALUATION_FIELDS:
        source_column = _find_column(history, FIELD_ALIASES[field], field)
        selected[field] = _numeric(history[source_column])

    selected = selected.dropna(subset=["date"])
    selected = selected[selected["date"].between(start, end)].copy()
    selected = selected.dropna(subset=list(VALUATION_FIELDS), how="all")
    if selected.empty:
        return _empty_valuation()

    selected = selected.sort_values("date").drop_duplicates("date", keep="last")
    selected.insert(1, "symbol", str(symbol).strip().upper())
    return selected[["date", "symbol", *VALUATION_FIELDS]].reset_index(drop=True)


def _default_valuation_fetcher(code: str) -> pd.DataFrame:
    try:
        import akshare as ak
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "缺少 AkShare，请先在项目根目录执行：pip install -e \".[akshare]\""
        ) from exc
    return ak.stock_value_em(symbol=code)


def _cache_path(
    cache_dir: Path,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Path:
    safe_symbol = symbol.replace(".", "_")
    return cache_dir / f"{safe_symbol}_{api_date(start)}_{api_date(end)}.parquet"


def _write_frame_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, engine="pyarrow", compression="zstd", index=False)
    temporary.replace(path)


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _cache_is_compatible(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        names = set(pq.read_schema(path).names)
    except (OSError, ValueError):
        return False
    return {"date", "symbol", *VALUATION_FIELDS}.issubset(names)


def _collect_dates(cache_paths: Sequence[Path]) -> pd.DatetimeIndex:
    dates: set[pd.Timestamp] = set()
    for path in cache_paths:
        if not _cache_is_compatible(path):
            continue
        table = pq.read_table(path, columns=["date"])
        values = pd.to_datetime(table.column("date").to_pandas(), errors="coerce")
        dates.update(item.normalize() for item in values.dropna())
        del values, table
    return pd.DatetimeIndex(sorted(dates), name="date")


def consolidate_wide(
    symbols: Sequence[str],
    cache_paths: Mapping[str, Path],
    output_path: Path,
    *,
    chunk_size: int = 64,
    force: bool = False,
) -> dict[str, object]:
    """从逐证券缓存分块生成十字段估值宽面板。"""

    if chunk_size <= 0:
        raise ValueError("chunk_size 必须为正数")
    if output_path.exists() and not force:
        raise FileExistsError(f"输出文件已存在（使用 --force 覆盖）：{output_path}")

    ordered_paths = [cache_paths[symbol] for symbol in symbols]
    dates = _collect_dates(ordered_paths)
    if len(dates) == 0:
        raise ValueError("没有可合并的历史估值缓存")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    columns = pd.MultiIndex.from_product(
        (symbols, VALUATION_FIELDS), names=("symbol", "field")
    )
    writer: Optional[pq.ParquetWriter] = None
    rows = 0
    try:
        for offset in range(0, len(dates), chunk_size):
            chunk_dates = dates[offset : offset + chunk_size]
            matrices = {
                field: np.full(
                    (len(chunk_dates), len(symbols)), np.nan, dtype="float64"
                )
                for field in VALUATION_FIELDS
            }
            for column_number, symbol in enumerate(symbols):
                path = cache_paths[symbol]
                if not _cache_is_compatible(path):
                    continue
                table = pq.read_table(path, columns=["date", *VALUATION_FIELDS])
                frame = table.to_pandas()
                frame["date"] = pd.to_datetime(
                    frame["date"], errors="coerce"
                ).dt.normalize()
                frame = (
                    frame.dropna(subset=["date"])
                    .sort_values("date")
                    .drop_duplicates("date", keep="last")
                )
                indexed = frame.set_index("date")
                for field in VALUATION_FIELDS:
                    values = pd.to_numeric(indexed[field], errors="coerce")
                    matrices[field][:, column_number] = values.reindex(
                        chunk_dates
                    ).to_numpy(dtype="float64")
                del indexed, frame, table

            data = {
                (symbol, field): matrices[field][:, column_number]
                for column_number, symbol in enumerate(symbols)
                for field in VALUATION_FIELDS
            }
            panel = pd.DataFrame(data, index=chunk_dates)
            panel.columns = columns
            panel.index.name = "date"
            table = pa.Table.from_pandas(panel, preserve_index=True)
            if writer is None:
                writer = pq.ParquetWriter(temporary, table.schema, compression="zstd")
            elif table.schema != writer.schema:
                table = table.cast(writer.schema)
            writer.write_table(table)
            rows += len(panel)
            del data, matrices, panel, table
    finally:
        if writer is not None:
            writer.close()
    temporary.replace(output_path)
    return {
        "output": output_path.as_posix(),
        "rows": rows,
        "symbols": len(symbols),
        "fields": list(VALUATION_FIELDS),
        "start_date": dates.min().strftime("%Y-%m-%d"),
        "end_date": dates.max().strftime("%Y-%m-%d"),
    }


def _fetch_one(
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    fetcher: ValuationFetcher,
    retries: int,
    retry_delay: float,
) -> pd.DataFrame:
    if retries <= 0:
        raise ValueError("retries 必须为正数")
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            raw = fetcher(symbol_to_code(symbol))
            return normalize_valuation(raw, symbol, start, end)
        except Exception as exc:  # network/provider errors are retriable
            last_error = exc
            if attempt + 1 < retries and retry_delay > 0:
                time.sleep(retry_delay * (attempt + 1))
    assert last_error is not None
    raise last_error


def run(
    *,
    start_date: str | date | pd.Timestamp,
    end_date: str | date | pd.Timestamp,
    data_root: Path = DEFAULT_DATA_ROOT,
    universe_path: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
    throttle_seconds: float = 0.5,
    retries: int = 3,
    retry_delay: float = 2.0,
    chunk_size: int = 64,
    force: bool = False,
    fetcher: Optional[ValuationFetcher] = None,
) -> dict[str, object]:
    """执行全 A 股十字段历史估值回填并生成候选宽面板。"""

    start, end = normalize_date_range(start_date, end_date)
    if throttle_seconds < 0 or retry_delay < 0:
        raise ValueError("限速和重试等待时间不能为负数")
    resolved_universe = universe_path or data_root / DEFAULT_UNIVERSE_RELATIVE
    symbols, _ = load_universe_mapping(resolved_universe)
    resolved_cache = cache_dir or data_root / DEFAULT_CACHE_RELATIVE
    resolved_output = output_path or (
        data_root
        / DEFAULT_OUTPUT_RELATIVE
        / f"daily_basic_{api_date(start)}_{api_date(end)}.parquet"
    )
    valuation_fetcher = fetcher or _default_valuation_fetcher
    cache_paths = {
        symbol: _cache_path(resolved_cache, symbol, start, end)
        for symbol in symbols
    }
    checkpoint_path = resolved_cache.parent / (
        f"checkpoint_{api_date(start)}_{api_date(end)}.json"
    )
    completed = 0
    empty = 0
    failed: list[dict[str, str]] = []
    cached = 0

    for position, symbol in enumerate(symbols, start=1):
        path = cache_paths[symbol]
        if _cache_is_compatible(path) and not force:
            cached += 1
        else:
            try:
                history = _fetch_one(
                    symbol, start, end, valuation_fetcher, retries, retry_delay
                )
                _write_frame_atomic(history, path)
                if history.empty:
                    empty += 1
                else:
                    completed += 1
            except Exception as exc:
                failed.append(
                    {"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"}
                )
        if throttle_seconds > 0 and position < len(symbols):
            time.sleep(throttle_seconds)
        if position == 1 or position % 50 == 0 or position == len(symbols):
            print(
                f"[{position}/{len(symbols)}] completed={completed} "
                f"cached={cached} empty={empty} failed={len(failed)}",
                flush=True,
            )
        _write_json_atomic(
            checkpoint_path,
            {
                "source": "akshare.stock_value_em",
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": end.strftime("%Y-%m-%d"),
                "last_position": position,
                "completed": completed,
                "cached": cached,
                "empty": empty,
                "failed": failed,
            },
        )

    panel_report = consolidate_wide(
        symbols,
        cache_paths,
        resolved_output,
        chunk_size=chunk_size,
        force=force,
    )
    report: dict[str, object] = {
        "source": "akshare.stock_value_em",
        "source_fields": {
            field: FIELD_ALIASES[field][0] for field in VALUATION_FIELDS
        },
        "fields": list(VALUATION_FIELDS),
        "units": FIELD_UNITS,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "universe_path": resolved_universe.as_posix(),
        "cache_dir": resolved_cache.as_posix(),
        "requested_symbols": len(symbols),
        "completed_symbols": completed,
        "cached_symbols": cached,
        "empty_symbols": empty,
        "failed_symbols": len(failed),
        "failed": failed,
        **panel_report,
    }
    _write_json_atomic(resolved_output.with_suffix(".json"), report)
    return report


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, help="历史起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="历史结束日期 YYYY-MM-DD")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--universe", type=Path, default=None)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.5,
        help="证券之间的串行请求间隔，默认 0.5 秒",
    )
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=64,
        help="合并宽表时每批日期数，默认 64",
    )
    parser.add_argument("--force", action="store_true", help="重新抓取并覆盖已有缓存和输出")
    args = parser.parse_args(argv)
    try:
        report = run(
            start_date=args.start_date,
            end_date=args.end_date,
            data_root=args.data_root,
            universe_path=args.universe,
            cache_dir=args.cache_dir,
            output_path=args.output,
            throttle_seconds=args.sleep_seconds,
            retries=args.retries,
            retry_delay=args.retry_delay,
            chunk_size=args.chunk_size,
            force=args.force,
        )
    except (FileNotFoundError, RuntimeError, TypeError, ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
