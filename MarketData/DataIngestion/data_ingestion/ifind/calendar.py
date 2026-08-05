"""iFinD 全 A 统一交易日历的全量回填与收盘后日增量下载。"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Protocol
from zoneinfo import ZoneInfo

from data_ingestion.ifind.client import IFindClient
from data_ingestion.ifind.raw import load_or_fetch_json


CALENDAR_ID = "ALL_A"
PRIMARY_EXCHANGE = "SZ"
PRIMARY_MARKETCODE = "212100"
PRIMARY_START_DATE = "1990-12-01"
CALENDAR_COLUMNS = ("date", "exchange", "is_trade_day", "source", "marketcode")


class CalendarClient(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def _iter_dates(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _iter_dates(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_dates(child)


def _normalize_date(value: str) -> str | None:
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def extract_trade_dates(response: dict) -> list[str]:
    if "tables" not in response:
        raise ValueError("iFinD 日期查询结果缺少 tables")
    dates = {_normalize_date(value) for value in _iter_dates(response["tables"])}
    return sorted(value for value in dates if value is not None)


def calendar_path(output_root: Path) -> Path:
    return output_root / "calendar" / f"{CALENDAR_ID}.csv"


def calendar_raw_path(output_root: Path, start: str, end: str) -> Path:
    return output_root / "calendar" / "raw" / CALENDAR_ID / f"{start}_{end}.json"


def _calendar_windows(start: str, end: str) -> Iterable[tuple[str, str]]:
    current, final = date.fromisoformat(start), date.fromisoformat(end)
    while current <= final:
        year_end = date(current.year, 12, 31)
        window_end = min(year_end, final)
        yield current.isoformat(), window_end.isoformat()
        current = window_end + timedelta(days=1)


def read_calendar_dates(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [row["date"] for row in csv.DictReader(stream)]


def write_calendar_csv(path: Path, dates: Iterable[str]) -> int:
    existing = set(read_calendar_dates(path))
    all_dates = sorted(existing | set(dates))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CALENDAR_COLUMNS)
        writer.writeheader()
        writer.writerows({
            "date": trade_date,
            "exchange": CALENDAR_ID,
            "is_trade_day": "true",
            "source": "ifind",
            "marketcode": PRIMARY_MARKETCODE,
        } for trade_date in all_dates)
    return len(all_dates) - len(existing)


def fetch_trade_dates(client: CalendarClient, start: str, end: str, raw_response_path: Path) -> list[str]:
    payload = {
        "marketcode": PRIMARY_MARKETCODE,
        "functionpara": {"mode": "1", "dateType": "0", "period": "D", "dateFormat": "0"},
        "startdate": start,
        "enddate": end,
    }
    response = load_or_fetch_json(client, raw_response_path, "/api/v1/get_trade_dates", payload)
    return extract_trade_dates(response)


def backfill_calendar(client: CalendarClient, output_root: Path, start: str, end: str) -> int:
    effective_start = max(start, PRIMARY_START_DATE)
    if effective_start > end:
        return 0
    path = calendar_path(output_root)
    total = 0
    for window_start, window_end in _calendar_windows(effective_start, end):
        total += write_calendar_csv(
            path,
            fetch_trade_dates(client, window_start, window_end, calendar_raw_path(output_root, window_start, window_end)),
        )
    return total


def update_calendar(client: CalendarClient, output_root: Path, as_of: str) -> int:
    path = calendar_path(output_root)
    existing = read_calendar_dates(path)
    if not existing:
        raise FileNotFoundError(f"缺少全量统一交易日历，请先执行 backfill：{path}")
    start = (date.fromisoformat(max(existing)) + timedelta(days=1)).isoformat()
    if start > as_of:
        return 0
    return write_calendar_csv(path, fetch_trade_dates(client, start, as_of, calendar_raw_path(output_root, start, as_of)))


def build_calendar_from_existing_sz(output_root: Path) -> int:
    """一次性迁移：由已有 SZ.csv 重建唯一维护的 ALL_A.csv，不访问网络。"""
    source_path = output_root / "calendar" / "SZ.csv"
    if not source_path.is_file():
        raise FileNotFoundError(f"缺少可迁移的深交所交易日历：{source_path}")
    return write_calendar_csv(calendar_path(output_root), read_calendar_dates(source_path))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backfill", "update", "build-from-existing-sz"))
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[3] / "sources" / "ifind")
    parser.add_argument("--start", help="全量回填起始日，格式 YYYY-MM-DD")
    parser.add_argument("--end", help="全量回填截止日，格式 YYYY-MM-DD")
    parser.add_argument("--as-of", help="日增量截至日期，默认上海时区当天")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.command == "build-from-existing-sz":
        result = build_calendar_from_existing_sz(args.output_root)
    elif args.command == "backfill":
        if not args.start or not args.end:
            raise SystemExit("backfill 必须提供 --start 和 --end")
        result = backfill_calendar(IFindClient.from_environment(), args.output_root, args.start, args.end)
    else:
        as_of = args.as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        result = update_calendar(IFindClient.from_environment(), args.output_root, as_of)
    print(json.dumps({"command": args.command, "new_trade_dates": {CALENDAR_ID: result}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
