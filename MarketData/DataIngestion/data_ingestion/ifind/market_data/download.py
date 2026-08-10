"""仅下载 iFinD 全 A 日频行情原始 JSON。"""

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
ADJUSTMENTS = ("hfq", "qfq", "none")
PRICE_FUNCTIONPARA = {"hfq": {"CPS": "1"}, "qfq": {"CPS": "2"}, "none": None}
PRICE = {"name": "price_hfq", "kind": "price", "fields": ("open", "high", "low", "close"), "root": ("prices", "hfq"), "functionpara": {"CPS": "1"}}
LIQUIDITY = {"name": "liquidity", "fields": ("volume", "amt", "turn"), "root": ("liquidity",), "functionpara": None}
DEFAULT_SYMBOLS_PER_REQUEST = 100
DEFAULT_TRADING_DAYS_PER_REQUEST = 10
DEFAULT_MAX_ESTIMATED_POINTS = 120_000_000


class MarketDataClient(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def price_group(adjustment: str) -> dict:
    if adjustment not in ADJUSTMENTS:
        raise ValueError(f"不支持的复权方式：{adjustment}")
    return {"name": f"price_{adjustment}", "kind": "price", "fields": ("open", "high", "low", "close"), "root": ("prices", adjustment), "functionpara": PRICE_FUNCTIONPARA[adjustment]}


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


def history_payload(group: dict, symbols: list[str], start: str, end: str) -> dict:
    body = {"codes": ",".join(symbols), "startdate": start, "enddate": end, "indicators": ",".join(group["fields"])}
    if group["functionpara"]:
        body["functionpara"] = group["functionpara"]
    return {"reqBody": body}


def raw_path(output_root: Path, group: dict, exchange: str, start: str, end: str, sequence: int) -> Path:
    return output_root.joinpath(*group["root"], "raw", exchange, f"{start}_{end}", f"symbols_{sequence:05d}.json")


def run_download(client: MarketDataClient, output_root: Path, universe_path: Path, start: str, end: str, symbols_per_request: int, trading_days_per_request: int, max_estimated_points: int, adjustment: str = "hfq") -> dict[str, dict[str, int]]:
    dates = read_trade_dates(calendar_path(output_root), start, end)
    date_batches = list(chunks(dates, trading_days_per_request))
    symbols_by_exchange = {exchange: list(chunks(read_universe_symbols(universe_path, exchange), symbols_per_request)) for exchange in EXCHANGES}
    total_batches = sum(len(date_batches) * len(symbol_batches) for symbol_batches in symbols_by_exchange.values())
    result: dict[str, dict[str, int]] = {}
    for group in (price_group(adjustment), LIQUIDITY):
        summary = {"raw_partitions": 0, "data_vol": 0, "estimated_points": 0, "skipped": 0}
        batch_number = 0
        for exchange in EXCHANGES:
            for date_batch in date_batches:
                for sequence, symbol_batch in enumerate(symbols_by_exchange[exchange], start=1):
                    batch_number += 1
                    path = raw_path(output_root, group, exchange, date_batch[0], date_batch[-1], sequence)
                    if path.is_file():
                        print(f"[{group['name']}] 第 {batch_number}/{total_batches} 批：{exchange} {date_batch[0]} 至 {date_batch[-1]}，已缓存，跳过", flush=True)
                        summary["skipped"] += 1
                        continue
                    points = len(symbol_batch) * len(date_batch) * len(group["fields"])
                    if summary["estimated_points"] + points > max_estimated_points:
                        print(f"[{group['name']}] 达到本次数据量上限，停止于第 {batch_number}/{total_batches} 批", flush=True)
                        result[group["name"]] = summary
                        break
                    print(f"[{group['name']}] 第 {batch_number}/{total_batches} 批：正在下载 {exchange} {date_batch[0]} 至 {date_batch[-1]}", flush=True)
                    response = load_or_fetch_json(client, path, "/api/v1/history_data", history_payload(group, symbol_batch, date_batch[0], date_batch[-1]))
                    summary["estimated_points"] += points
                    summary["data_vol"] += int(response.get("dataVol", 0) or 0)
                    summary["raw_partitions"] += 1
                else:
                    continue
                break
            else:
                result[group["name"]] = summary
                continue
            result[group["name"]] = summary
    return result


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
    parser.add_argument("--adjustment", choices=ADJUSTMENTS, default="hfq", help="价格复权方式：hfq=后复权，qfq=前复权，none=不复权")
    args = parser.parse_args()
    if args.command == "backfill" and (not args.start or not args.end):
        raise SystemExit("backfill 必须提供 --start 和 --end")
    start = args.start if args.command == "backfill" else args.as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    end = args.end if args.command == "backfill" else start
    universe = args.universe or existing_universe_path(args.output_root)
    print(json.dumps(run_download(IFindClient.from_environment(), args.output_root, universe, start, end, args.symbols_per_request, args.trading_days_per_request if args.command == "backfill" else 1, args.max_estimated_points, args.adjustment), ensure_ascii=False))


if __name__ == "__main__":
    main()
