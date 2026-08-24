"""下载 iFinD 指数 OHLC 历史行情原始 JSON。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from data_ingestion.ifind.calendar.pipeline import calendar_path
from data_ingestion.ifind.common.client import IFindClient
from data_ingestion.ifind.common.history import (
    DEFAULT_MAX_ESTIMATED_POINTS,
    DEFAULT_TRADING_DAYS_PER_REQUEST,
    HistoryDataClient,
    chunks,
    history_payload,
    read_trade_dates,
)
from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.common.raw import load_or_fetch_json

INDEX_PRICE = {
    "name": "index_price",
    "fields": ("high", "open", "low", "close"),
    "functionpara": None,
}
OUTPUT_DIR = Path("index") / "index_price"
OUTPUT_PREFIX = "index_price"


def artifact_path(output_root: Path, index_code: str, suffix: str) -> Path:
    return output_root / OUTPUT_DIR / f"{OUTPUT_PREFIX}_{index_code}.{suffix}"


def raw_path(output_root: Path, index_code: str, start: str, end: str) -> Path:
    return output_root / OUTPUT_DIR / "raw" / index_code / f"{start}_{end}.json"


def run_download(
    client: HistoryDataClient,
    output_root: Path,
    index_code: str,
    start: str,
    end: str,
    trading_days_per_request: int = DEFAULT_TRADING_DAYS_PER_REQUEST,
    max_estimated_points: int = DEFAULT_MAX_ESTIMATED_POINTS,
) -> dict[str, int]:
    dates = read_trade_dates(calendar_path(output_root), start, end)
    date_batches = list(chunks(dates, trading_days_per_request))
    summary = {"raw_partitions": 0, "data_vol": 0, "estimated_points": 0, "skipped": 0}
    for number, date_batch in enumerate(date_batches, start=1):
        batch_start, batch_end = date_batch[0], date_batch[-1]
        path = raw_path(output_root, index_code, batch_start, batch_end)
        if path.is_file():
            print(
                f"[index_price] 第 {number}/{len(date_batches)} 批："
                f"{index_code} {batch_start} 至 {batch_end}，已缓存，跳过",
                flush=True,
            )
            summary["skipped"] += 1
            continue
        points = len(date_batch) * len(INDEX_PRICE["fields"])
        if summary["estimated_points"] + points > max_estimated_points:
            print(f"[index_price] 达到本次数据量上限，停止于第 {number}/{len(date_batches)} 批", flush=True)
            break
        print(
            f"[index_price] 第 {number}/{len(date_batches)} 批："
            f"正在下载 {index_code} {batch_start} 至 {batch_end}",
            flush=True,
        )
        response = load_or_fetch_json(
            client,
            path,
            "/api/v1/history_data",
            history_payload(INDEX_PRICE, [index_code], batch_start, batch_end),
        )
        summary["estimated_points"] += points
        summary["data_vol"] += int(response.get("dataVol", 0) or 0)
        summary["raw_partitions"] += 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backfill", "update"))
    parser.add_argument("--index", default="000300.SH", help="iFinD 指数代码，默认 000300.SH（沪深 300）")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--as-of")
    parser.add_argument("--trading-days-per-request", type=int, default=DEFAULT_TRADING_DAYS_PER_REQUEST)
    parser.add_argument("--max-estimated-points", type=int, default=DEFAULT_MAX_ESTIMATED_POINTS)
    args = parser.parse_args()
    if args.command == "backfill" and (not args.start or not args.end):
        raise SystemExit("backfill 必须提供 --start 和 --end")
    start = args.start if args.command == "backfill" else args.as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    end = args.end if args.command == "backfill" else start
    result = run_download(
        IFindClient.from_environment(),
        args.output_root,
        args.index,
        start,
        end,
        args.trading_days_per_request if args.command == "backfill" else 1,
        args.max_estimated_points,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
