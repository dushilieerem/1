"""iFinD 全 A 后复权日频 OHLC 的全量回填与收盘后日增量脚本。"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import Iterator, Protocol
from zoneinfo import ZoneInfo

from data_ingestion.ifind.client import IFindClient
from data_ingestion.ifind.calendar import calendar_path
from data_ingestion.ifind.raw import load_or_fetch_json


FIELDS = ("open", "high", "low", "close")
EXCHANGES = ("SH", "SZ", "BJ")
CSV_COLUMNS = ("date", "thscode", "exchange", *FIELDS, "adjustment", "source")
DEFAULT_SYMBOLS_PER_REQUEST = 100
DEFAULT_TRADING_DAYS_PER_REQUEST = 10
DEFAULT_MAX_ESTIMATED_POINTS = 120_000_000


class PriceClient(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def _chunks(values: list[str], size: int) -> Iterator[list[str]]:
    if size <= 0:
        raise ValueError("批次大小必须大于零")
    iterator = iter(values)
    while batch := list(islice(iterator, size)):
        yield batch


def _normalize_date(value: str) -> str:
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"iFinD 返回无效日期：{value}")


def read_universe_symbols(path: Path, exchange: str) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    symbols = [row["thscode"] for row in rows if row.get("exchange") == exchange]
    if not symbols:
        raise ValueError(f"证券池中没有 {exchange} 证券：{path}")
    if len(symbols) != len(set(symbols)):
        raise ValueError(f"证券池中 {exchange} 存在重复证券代码")
    return symbols


def read_trade_dates(path: Path, start: str, end: str) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        dates = [row["date"] for row in csv.DictReader(stream)]
    return [trade_date for trade_date in dates if start <= trade_date <= end]


def history_payload(symbols: list[str], start: str, end: str) -> dict:
    return {
        "reqBody": {
            "codes": ",".join(symbols),
            "startdate": start,
            "enddate": end,
            "indicators": ",".join(FIELDS),
            "functionpara": {"CPS": "1"},
        }
    }


def normalize_history_response(response: dict, exchange: str) -> list[dict[str, object]]:
    tables = response.get("tables")
    if not isinstance(tables, list):
        raise ValueError("iFinD 历史行情返回缺少 tables")

    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in tables:
        if not isinstance(item, dict):
            raise ValueError("iFinD 历史行情 tables 包含非对象")
        thscode, times, table = item.get("thscode"), item.get("time"), item.get("table")
        if not isinstance(thscode, str) or not isinstance(times, list) or not isinstance(table, dict):
            raise ValueError("iFinD 历史行情单证券结果缺少 thscode、time 或 table")
        columns = {field: table.get(field) for field in FIELDS}
        if any(not isinstance(values, list) or len(values) != len(times) for values in columns.values()):
            raise ValueError(f"iFinD OHLC 长度不一致：{thscode}")
        for index, raw_date in enumerate(times):
            trade_date = _normalize_date(str(raw_date))
            key = (trade_date, thscode)
            if key in seen:
                raise ValueError(f"iFinD 历史行情存在重复记录：{trade_date} {thscode}")
            seen.add(key)
            values = {field: columns[field][index] for field in FIELDS}
            present = [value for value in values.values() if value is not None]
            if present and len(present) != len(FIELDS):
                raise ValueError(f"iFinD OHLC 部分缺失：{trade_date} {thscode}")
            if len(present) == len(FIELDS):
                open_, high, low, close = (float(values[field]) for field in FIELDS)
                if high < max(open_, close) or low > min(open_, close) or high < low:
                    raise ValueError(f"iFinD OHLC 关系异常：{trade_date} {thscode}")
            rows.append({
                "date": trade_date,
                "thscode": thscode,
                "exchange": exchange,
                **values,
                "adjustment": "hfq",
                "source": "ifind",
            })
    return sorted(rows, key=lambda row: (str(row["date"]), str(row["thscode"])))


def price_paths(output_root: Path, exchange: str, start: str, end: str, sequence: int) -> tuple[Path, Path]:
    name = f"symbols_{sequence:05d}.json"
    raw = output_root / "prices" / "hfq" / "raw" / exchange / f"{start}_{end}" / name
    csv_path = output_root / "prices" / "hfq" / "csv" / exchange / f"{start}_{end}" / name.replace(".json", ".csv")
    return raw, csv_path


def write_price_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)


def _download_batch(
    client: PriceClient,
    output_root: Path,
    exchange: str,
    symbols: list[str],
    start: str,
    end: str,
    sequence: int,
) -> tuple[int, int, bool]:
    raw_path, csv_path = price_paths(output_root, exchange, start, end, sequence)
    if csv_path.is_file():
        return 0, 0, True
    response = load_or_fetch_json(client, raw_path, "/api/v1/history_data", history_payload(symbols, start, end))
    rows = normalize_history_response(response, exchange)
    returned_symbols = {str(row["thscode"]) for row in rows}
    if not returned_symbols.issubset(set(symbols)):
        raise ValueError("iFinD 历史行情返回了请求之外的证券")
    write_price_csv(csv_path, rows)
    return len(rows), int(response.get("dataVol", 0) or 0), False


def _run(
    client: PriceClient,
    output_root: Path,
    universe_path: Path,
    start: str,
    end: str,
    symbols_per_request: int,
    trading_days_per_request: int,
    max_estimated_points: int,
) -> dict[str, int]:
    summary = {"csv_partitions": 0, "rows": 0, "data_vol": 0, "estimated_points": 0, "skipped": 0}
    for exchange in EXCHANGES:
        symbols = read_universe_symbols(universe_path, exchange)
        trade_dates = read_trade_dates(calendar_path(output_root), start, end)
        for date_batch in _chunks(trade_dates, trading_days_per_request):
            for sequence, symbol_batch in enumerate(_chunks(symbols, symbols_per_request), start=1):
                raw_path, csv_path = price_paths(output_root, exchange, date_batch[0], date_batch[-1], sequence)
                estimated_points = len(symbol_batch) * len(date_batch) * len(FIELDS)
                if not raw_path.is_file() and not csv_path.is_file():
                    if summary["estimated_points"] + estimated_points > max_estimated_points:
                        return summary
                    summary["estimated_points"] += estimated_points
                rows, data_vol, skipped = _download_batch(
                    client, output_root, exchange, symbol_batch, date_batch[0], date_batch[-1], sequence
                )
                summary["rows"] += rows
                summary["data_vol"] += data_vol
                if skipped:
                    summary["skipped"] += 1
                else:
                    summary["csv_partitions"] += 1
    return summary


def backfill_prices(
    client: PriceClient,
    output_root: Path,
    universe_path: Path,
    start: str,
    end: str,
    symbols_per_request: int = DEFAULT_SYMBOLS_PER_REQUEST,
    trading_days_per_request: int = DEFAULT_TRADING_DAYS_PER_REQUEST,
    max_estimated_points: int = DEFAULT_MAX_ESTIMATED_POINTS,
) -> dict[str, int]:
    return _run(client, output_root, universe_path, start, end, symbols_per_request, trading_days_per_request, max_estimated_points)


def update_prices(
    client: PriceClient,
    output_root: Path,
    universe_path: Path,
    as_of: str,
    symbols_per_request: int = DEFAULT_SYMBOLS_PER_REQUEST,
    max_estimated_points: int = DEFAULT_MAX_ESTIMATED_POINTS,
) -> dict[str, int]:
    return _run(client, output_root, universe_path, as_of, as_of, symbols_per_request, 1, max_estimated_points)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backfill", "update"))
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[3] / "sources" / "ifind")
    parser.add_argument("--universe", type=Path)
    parser.add_argument("--start", help="全量回填起始日，格式 YYYY-MM-DD")
    parser.add_argument("--end", help="全量回填截止日，格式 YYYY-MM-DD")
    parser.add_argument("--as-of", help="收盘后日增量目标日，默认上海时区当天")
    parser.add_argument("--symbols-per-request", type=int, default=DEFAULT_SYMBOLS_PER_REQUEST)
    parser.add_argument("--trading-days-per-request", type=int, default=DEFAULT_TRADING_DAYS_PER_REQUEST)
    parser.add_argument("--max-estimated-points", type=int, default=DEFAULT_MAX_ESTIMATED_POINTS)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    universe_path = args.universe or args.output_root / "universe" / "a_share_5537.csv"
    client = IFindClient.from_environment()
    if args.command == "backfill":
        if not args.start or not args.end:
            raise SystemExit("backfill 必须提供 --start 和 --end")
        summary = backfill_prices(
            client, args.output_root, universe_path, args.start, args.end,
            args.symbols_per_request, args.trading_days_per_request, args.max_estimated_points,
        )
    else:
        as_of = args.as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        summary = update_prices(
            client, args.output_root, universe_path, as_of,
            args.symbols_per_request, args.max_estimated_points,
        )
    print(json.dumps({"command": args.command, **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
