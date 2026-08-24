"""仅下载 iFinD 指数成分股权重原始 JSON。"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from data_ingestion.ifind.calendar.pipeline import calendar_path
from data_ingestion.ifind.common.client import IFindClient
from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.common.raw import load_or_fetch_json

REPORT_NAME = "p03563"
OUTPUT_FIELDS = ("p03563_f002", "p03563_f004")
OUTPUT_DIR = Path("index") / "index_weights"
OUTPUT_PREFIX = "index_weights"


def artifact_path(output_root: Path, index_code: str, suffix: str) -> Path:
    return output_root / OUTPUT_DIR / f"{OUTPUT_PREFIX}_{index_code}.{suffix}"


class IndexWeightsClient(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def read_trade_dates(path: Path, start: str, end: str) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [row["date"] for row in csv.DictReader(stream) if start <= row["date"] <= end]


def index_weights_payload(index_code: str, date: str) -> dict:
    return {
        "reportname": REPORT_NAME,
        "functionpara": {"date": date.replace("-", ""), "index_name": index_code},
        "outputpara": ",".join(OUTPUT_FIELDS),
    }


def raw_path(output_root: Path, index_code: str, date: str) -> Path:
    return output_root / OUTPUT_DIR / "raw" / index_code / f"{date}.json"


def run_download(client: IndexWeightsClient, output_root: Path, index_code: str, start: str, end: str) -> dict[str, int]:
    dates = read_trade_dates(calendar_path(output_root), start, end)
    summary = {"raw_partitions": 0, "data_vol": 0, "skipped": 0}
    for number, date in enumerate(dates, start=1):
        path = raw_path(output_root, index_code, date)
        if path.is_file():
            print(f"[index_weights] 第 {number}/{len(dates)} 日：{index_code} {date}，已缓存，跳过", flush=True)
            summary["skipped"] += 1
            continue
        print(f"[index_weights] 第 {number}/{len(dates)} 日：正在下载 {index_code} {date}", flush=True)
        response = load_or_fetch_json(client, path, "/api/v1/data_pool", index_weights_payload(index_code, date))
        summary["raw_partitions"] += 1
        summary["data_vol"] += int(response.get("dataVol", 0) or 0)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backfill", "update"))
    parser.add_argument("--index", default="000300.SH", help="iFinD 指数代码，默认 000300.SH（沪深 300）")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--as-of")
    args = parser.parse_args()
    if args.command == "backfill" and (not args.start or not args.end):
        raise SystemExit("backfill 必须提供 --start 和 --end")
    start = args.start if args.command == "backfill" else args.as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    end = args.end if args.command == "backfill" else start
    print(json.dumps(run_download(IFindClient.from_environment(), args.output_root, args.index, start, end), ensure_ascii=False))


if __name__ == "__main__":
    main()
