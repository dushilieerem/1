"""按依赖顺序执行 iFinD 每日数据更新。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Protocol

from data_ingestion.ifind.calendar.pipeline import (
    CALENDAR_CSV_FILENAME,
    CALENDAR_PARQUET_FILENAME,
    default_update_as_of,
    update_calendar,
)
from data_ingestion.ifind.common.client import IFindClient
from data_ingestion.ifind.common.parquet import csv_to_flat_parquet
from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.index.index_price.csv import update_index_price_csv
from data_ingestion.ifind.index.index_price.download import (
    artifact_path as index_price_artifact_path,
    run_download as download_index_price,
)
from data_ingestion.ifind.index.index_price.parquet import csv_to_index_price_parquet
from data_ingestion.ifind.index.index_weights.csv import update_index_weights_csv
from data_ingestion.ifind.index.index_weights.download import (
    artifact_path as index_weights_artifact_path,
    run_download as download_index_weights,
)
from data_ingestion.ifind.index.index_weights.parquet import csv_to_index_weights_parquet
from data_ingestion.ifind.market_data.csv import (
    DEFAULT_WORKERS,
    OUTPUT_DIR as MARKET_DATA_DIR,
    OUTPUT_FILENAME as MARKET_DATA_CSV_FILENAME,
    update_daily_csv,
)
from data_ingestion.ifind.market_data.download import (
    DEFAULT_MAX_ESTIMATED_POINTS,
    DEFAULT_SYMBOLS_PER_REQUEST,
    run_download as download_market_data,
)
from data_ingestion.ifind.market_data.parquet import (
    OUTPUT_PARQUET_FILENAME as MARKET_DATA_PARQUET_FILENAME,
    csv_to_parquet,
)
from data_ingestion.ifind.universe.pipeline import (
    existing_universe_path,
    run_universe_download,
    update_universe_csv,
)


class EverydayUpdateClient(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def run_everyday_update(
    client: EverydayUpdateClient,
    output_root: Path,
    as_of: str,
    index_code: str = "000300.SH",
    workers: int = DEFAULT_WORKERS,
) -> dict[str, object]:
    """执行交易日历、证券池/指数数据和股票行情的完整日更新。"""
    print(f"[everydayupdate] 目标日期：{as_of}", flush=True)

    print("[everydayupdate] 第 1/3 步：更新交易日历", flush=True)
    calendar_added = update_calendar(client, output_root, as_of)
    calendar_dir = output_root / "calendar"
    calendar_parquet = csv_to_flat_parquet(
        calendar_dir / CALENDAR_CSV_FILENAME,
        calendar_dir / CALENDAR_PARQUET_FILENAME,
        "calendar_parquet",
    )

    print("[everydayupdate] 第 2/3 步：更新股票池、指数权重和指数价格", flush=True)
    universe_download = run_universe_download(client, output_root, as_of)
    universe_csv = update_universe_csv(output_root, as_of)
    universe_parquet = csv_to_flat_parquet(
        existing_universe_path(output_root),
        output_root / "universe" / "a_share.parquet",
        "universe_parquet",
    )
    index_download = download_index_weights(
        client, output_root, index_code, as_of, as_of
    )
    index_csv = update_index_weights_csv(output_root, index_code, as_of)
    index_weights_parquet = csv_to_index_weights_parquet(
        index_weights_artifact_path(output_root, index_code, "csv"),
        index_weights_artifact_path(output_root, index_code, "parquet"),
    )
    index_price_download = download_index_price(
        client, output_root, index_code, as_of, as_of, 1, DEFAULT_MAX_ESTIMATED_POINTS
    )
    index_price_csv = update_index_price_csv(output_root, index_code, as_of)
    index_price_parquet = csv_to_index_price_parquet(
        index_price_artifact_path(output_root, index_code, "csv"),
        index_price_artifact_path(output_root, index_code, "parquet"),
    )

    print("[everydayupdate] 第 3/3 步：更新行情数据", flush=True)
    universe_path = existing_universe_path(output_root)
    market_download = download_market_data(
        client,
        output_root,
        universe_path,
        as_of,
        as_of,
        DEFAULT_SYMBOLS_PER_REQUEST,
        1,
        DEFAULT_MAX_ESTIMATED_POINTS,
    )
    market_csv = update_daily_csv(output_root, as_of, workers, universe_path)
    market_dir = output_root / MARKET_DATA_DIR
    market_parquet = csv_to_parquet(
        market_dir / MARKET_DATA_CSV_FILENAME,
        market_dir / MARKET_DATA_PARQUET_FILENAME,
    )

    return {
        "as_of": as_of,
        "calendar": {"new_trade_dates": calendar_added, "parquet": calendar_parquet},
        "reference_data": {
            "universe": {
                "download": universe_download,
                "csv": universe_csv,
                "parquet": universe_parquet,
            },
            "index": {
                "code": index_code,
                "weights": {
                    "download": index_download,
                    "csv": index_csv,
                    "parquet": index_weights_parquet,
                },
                "price": {
                    "download": index_price_download,
                    "csv": index_price_csv,
                    "parquet": index_price_parquet,
                },
            },
        },
        "market_data": {
            "adjustment": "hfq",
            "download": market_download,
            "csv": market_csv,
            "parquet": market_parquet,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--as-of",
        help="目标日期；未指定时上海时间 17:00 前取前一日，17:00 起取当天",
    )
    parser.add_argument(
        "--index", default="000300.SH", help="更新的 iFinD 指数代码，默认沪深 300"
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summary = run_everyday_update(
        IFindClient.from_environment(),
        args.output_root,
        args.as_of or default_update_as_of(),
        args.index,
        args.workers,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
