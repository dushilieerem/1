"""仅下载供 WebApp K 线展示使用的 iFinD 未复权 OHLC 原始 JSON。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from data_ingestion.ifind.common.client import IFindClient
from data_ingestion.ifind.common.history import (
    DEFAULT_MAX_ESTIMATED_POINTS,
    DEFAULT_SYMBOLS_PER_REQUEST,
    DEFAULT_TRADING_DAYS_PER_REQUEST,
    HistoryDataClient,
    history_payload,
    run_history_download,
)
from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.universe.pipeline import existing_universe_path

PRICE = {
    "name": "price_none",
    "fields": ("open", "high", "low", "close"),
    "raw_root": ("unadjusted_price", "raw"),
    "functionpara": None,
}


def run_download(
    client: HistoryDataClient,
    output_root: Path,
    universe_path: Path,
    start: str,
    end: str,
    symbols_per_request: int,
    trading_days_per_request: int,
    max_estimated_points: int,
) -> dict[str, dict[str, int]]:
    return run_history_download(
        client,
        output_root,
        universe_path,
        start,
        end,
        symbols_per_request,
        trading_days_per_request,
        max_estimated_points,
        (PRICE,),
    )


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
    result = run_download(
        IFindClient.from_environment(),
        args.output_root,
        universe,
        start,
        end,
        args.symbols_per_request,
        args.trading_days_per_request if args.command == "backfill" else 1,
        args.max_estimated_points,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
