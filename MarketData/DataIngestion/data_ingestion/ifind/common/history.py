"""iFinD history_data 下载任务的共享批处理能力。"""

from __future__ import annotations

import csv
from itertools import islice
from pathlib import Path
from typing import Iterable, Iterator, Protocol

from data_ingestion.ifind.calendar.pipeline import calendar_path
from data_ingestion.ifind.common.raw import load_or_fetch_json

EXCHANGES = ("SH", "SZ", "BJ")
DEFAULT_SYMBOLS_PER_REQUEST = 100
DEFAULT_TRADING_DAYS_PER_REQUEST = 10
DEFAULT_MAX_ESTIMATED_POINTS = 120_000_000


class HistoryDataClient(Protocol):
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


def history_payload(group: dict, symbols: list[str], start: str, end: str) -> dict:
    body = {
        "codes": ",".join(symbols),
        "startdate": start,
        "enddate": end,
        "indicators": ",".join(group["fields"]),
    }
    if group.get("functionpara"):
        body["functionpara"] = group["functionpara"]
    return {"reqBody": body}


def raw_path(output_root: Path, group: dict, exchange: str, start: str, end: str, sequence: int) -> Path:
    return output_root.joinpath(
        *group["raw_root"], exchange, f"{start}_{end}", f"symbols_{sequence:05d}.json"
    )


def run_history_download(
    client: HistoryDataClient,
    output_root: Path,
    universe_path: Path,
    start: str,
    end: str,
    symbols_per_request: int,
    trading_days_per_request: int,
    max_estimated_points: int,
    groups: Iterable[dict],
) -> dict[str, dict[str, int]]:
    dates = read_trade_dates(calendar_path(output_root), start, end)
    date_batches = list(chunks(dates, trading_days_per_request))
    symbols_by_exchange = {
        exchange: list(chunks(read_universe_symbols(universe_path, exchange), symbols_per_request))
        for exchange in EXCHANGES
    }
    total_batches = sum(
        len(date_batches) * len(symbol_batches)
        for symbol_batches in symbols_by_exchange.values()
    )
    result: dict[str, dict[str, int]] = {}
    for group in groups:
        summary = {"raw_partitions": 0, "data_vol": 0, "estimated_points": 0, "skipped": 0}
        batch_number = 0
        stopped = False
        for exchange in EXCHANGES:
            for date_batch in date_batches:
                for sequence, symbol_batch in enumerate(symbols_by_exchange[exchange], start=1):
                    batch_number += 1
                    path = raw_path(
                        output_root,
                        group,
                        exchange,
                        date_batch[0],
                        date_batch[-1],
                        sequence,
                    )
                    if path.is_file():
                        print(
                            f"[{group['name']}] 第 {batch_number}/{total_batches} 批："
                            f"{exchange} {date_batch[0]} 至 {date_batch[-1]}，已缓存，跳过",
                            flush=True,
                        )
                        summary["skipped"] += 1
                        continue
                    points = len(symbol_batch) * len(date_batch) * len(group["fields"])
                    if summary["estimated_points"] + points > max_estimated_points:
                        print(
                            f"[{group['name']}] 达到本次数据量上限，停止于第 "
                            f"{batch_number}/{total_batches} 批",
                            flush=True,
                        )
                        stopped = True
                        break
                    print(
                        f"[{group['name']}] 第 {batch_number}/{total_batches} 批："
                        f"正在下载 {exchange} {date_batch[0]} 至 {date_batch[-1]}",
                        flush=True,
                    )
                    response = load_or_fetch_json(
                        client,
                        path,
                        "/api/v1/history_data",
                        history_payload(group, symbol_batch, date_batch[0], date_batch[-1]),
                    )
                    summary["estimated_points"] += points
                    summary["data_vol"] += int(response.get("dataVol", 0) or 0)
                    summary["raw_partitions"] += 1
                if stopped:
                    break
            if stopped:
                break
        result[group["name"]] = summary
    return result
