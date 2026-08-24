"""仅下载 iFinD 全 A 日期序列原始 JSON。"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import Iterator, Protocol
from zoneinfo import ZoneInfo

from data_ingestion.ifind.calendar.pipeline import calendar_path
from data_ingestion.ifind.common.client import IFindClient
from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.common.raw import load_or_fetch_json
from data_ingestion.ifind.universe.pipeline import existing_universe_path

EXCHANGES = ("SH", "SZ", "BJ")
SOURCE_FIELDS = ("ths_current_mv_stock", "ths_pe_stock", "ths_pb_stock", "ths_the_sw_industry_stock", "ths_the_sw_industry_code_stock", "ths_up_and_down_status_stock")
INDIPARA = (
    {"indicator": "ths_current_mv_stock", "indiparams": [""]}, {"indicator": "ths_pe_stock", "indiparams": ["", "100"]},
    {"indicator": "ths_pb_stock", "indiparams": ["", "100"]}, {"indicator": "ths_the_sw_industry_stock", "indiparams": ["1", ""]},
    {"indicator": "ths_the_sw_industry_code_stock", "indiparams": ["1", ""]}, {"indicator": "ths_up_and_down_status_stock", "indiparams": [""]},
)
DEFAULT_SYMBOLS_PER_REQUEST = 100
DEFAULT_TRADING_DAYS_PER_REQUEST = 10
DEFAULT_MAX_ESTIMATED_POINTS = 4_500_000


class DateSequenceClient(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def chunks(values: list[str], size: int) -> Iterator[list[str]]:
    if size <= 0:
        raise ValueError("批次大小必须大于零")
    iterator = iter(values)
    while batch := list(islice(iterator, size)):
        yield batch


def read_universe_symbols(path: Path, exchange: str) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        symbols = []
        for row in csv.DictReader(stream):
            thscode = str(row.get("thscode", "")).strip()
            row_exchange = str(row.get("exchange", "")).strip() or thscode.rsplit(".", 1)[-1]
            if thscode and row_exchange == exchange:
                symbols.append(thscode)
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError(f"证券池 {exchange} 缺失或存在重复代码：{path}")
    return symbols


def read_trade_dates(path: Path, start: str, end: str) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [row["date"] for row in csv.DictReader(stream) if start <= row["date"] <= end]


def date_sequence_payload(symbols: list[str], start: str, end: str) -> dict:
    return {"codes": ",".join(symbols), "functionpara": {"Fill": "Blank"}, "startdate": start, "enddate": end, "indipara": list(INDIPARA)}


def raw_path(output_root: Path, exchange: str, start: str, end: str, sequence: int) -> Path:
    return output_root / "date_sequence" / "raw" / exchange / f"{start}_{end}" / f"symbols_{sequence:05d}.json"


def run_download(client: DateSequenceClient, output_root: Path, universe_path: Path, start: str, end: str, symbols_per_request: int, trading_days_per_request: int, max_estimated_points: int) -> dict[str, int]:
    summary = {"raw_partitions": 0, "data_vol": 0, "estimated_points": 0, "skipped": 0}
    date_batches = list(chunks(read_trade_dates(calendar_path(output_root), start, end), trading_days_per_request))
    symbols_by_exchange = {exchange: list(chunks(read_universe_symbols(universe_path, exchange), symbols_per_request)) for exchange in EXCHANGES}
    total_batches = sum(len(date_batches) * len(symbol_batches) for symbol_batches in symbols_by_exchange.values())
    batch_number = 0
    for exchange in EXCHANGES:
        for date_batch in date_batches:
            for sequence, symbol_batch in enumerate(symbols_by_exchange[exchange], start=1):
                batch_number += 1
                path = raw_path(output_root, exchange, date_batch[0], date_batch[-1], sequence)
                if path.is_file():
                    print(f"[date_sequence] 第 {batch_number}/{total_batches} 批：{exchange} {date_batch[0]} 至 {date_batch[-1]}，已缓存，跳过", flush=True)
                    summary["skipped"] += 1
                    continue
                points = len(symbol_batch) * len(date_batch) * len(SOURCE_FIELDS)
                if summary["estimated_points"] + points > max_estimated_points:
                    print(f"[date_sequence] 达到本次数据量上限，停止于第 {batch_number}/{total_batches} 批", flush=True)
                    return summary
                print(f"[date_sequence] 第 {batch_number}/{total_batches} 批：正在下载 {exchange} {date_batch[0]} 至 {date_batch[-1]}", flush=True)
                response = load_or_fetch_json(client, path, "/api/v1/date_sequence", date_sequence_payload(symbol_batch, date_batch[0], date_batch[-1]))
                summary["estimated_points"] += points
                summary["data_vol"] += int(response.get("dataVol", 0) or 0)
                summary["raw_partitions"] += 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backfill", "update"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--universe", type=Path)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--as-of")
    parser.add_argument("--symbols-per-request", type=int, default=DEFAULT_SYMBOLS_PER_REQUEST)
    parser.add_argument("--trading-days-per-request", type=int, default=DEFAULT_TRADING_DAYS_PER_REQUEST)
    parser.add_argument("--max-estimated-points", type=int, default=DEFAULT_MAX_ESTIMATED_POINTS)
    args = parser.parse_args()
    if args.command == "backfill" and (not args.start or not args.end):
        raise SystemExit("backfill 必须提供 --start 和 --end")
    start = args.start if args.command == "backfill" else args.as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    end = args.end if args.command == "backfill" else start
    universe = args.universe or existing_universe_path(args.output_root)
    print(json.dumps(run_download(IFindClient.from_environment(), args.output_root, universe, start, end, args.symbols_per_request, args.trading_days_per_request if args.command == "backfill" else 1, args.max_estimated_points), ensure_ascii=False))


if __name__ == "__main__":
    main()
