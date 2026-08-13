"""按依赖顺序执行 iFinD 每日数据更新。"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Protocol

from data_ingestion.ifind.calendar.pipeline import (
    CALENDAR_CSV_FILENAME,
    CALENDAR_PARQUET_FILENAME,
    default_update_as_of,
    read_calendar_dates,
    update_calendar,
)
from data_ingestion.ifind.common.client import IFindClient
from data_ingestion.ifind.common.parquet import csv_to_flat_parquet
from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.index.index_price.csv import update_index_price_csv_range
from data_ingestion.ifind.index.index_price.download import (
    artifact_path as index_price_artifact_path,
    run_download as download_index_price,
)
from data_ingestion.ifind.index.index_price.parquet import csv_to_index_price_parquet
from data_ingestion.ifind.index.index_weights.csv import update_index_weights_csv_range
from data_ingestion.ifind.index.index_weights.download import (
    artifact_path as index_weights_artifact_path,
    run_download as download_index_weights,
)
from data_ingestion.ifind.index.index_weights.parquet import csv_to_index_weights_parquet
from data_ingestion.ifind.market_data.csv import (
    DEFAULT_WORKERS,
    OUTPUT_DIR as MARKET_DATA_DIR,
    OUTPUT_FILENAME as MARKET_DATA_CSV_FILENAME,
    update_daily_csv_range,
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
from data_ingestion.ifind.unadjusted_price.csv import (
    OUTPUT_DIR as UNADJUSTED_PRICE_DIR,
    OUTPUT_FILENAME as UNADJUSTED_PRICE_CSV_FILENAME,
    update_price_csv_range,
)
from data_ingestion.ifind.unadjusted_price.download import (
    run_download as download_unadjusted_price,
)
from data_ingestion.ifind.unadjusted_price.parquet import (
    OUTPUT_PARQUET_FILENAME as UNADJUSTED_PRICE_PARQUET_FILENAME,
    csv_to_parquet as csv_to_unadjusted_price_parquet,
)
from data_ingestion.ifind.universe.pipeline import (
    existing_universe_path,
    run_universe_download,
    update_universe_csv,
)

# 每日总更新维护的指数。增删指数只需修改此列表。
INDEX_CODES = [
    "000300.SH",
    "000905.SH",
]


class EverydayUpdateClient(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def _latest_csv_date(path: Path) -> str | None:
    """读取按日期升序 CSV 的最后一个有效日期，不扫描整个大文件。"""
    if not path.is_file() or path.stat().st_size == 0:
        return None
    size = path.stat().st_size
    window = min(size, 64 * 1024)
    with path.open("rb") as stream:
        while True:
            start = max(0, size - window)
            stream.seek(start)
            lines = stream.read().splitlines()
            if start == 0 or len(lines) >= 2:
                for line in reversed(lines):
                    candidate = line.split(b",", 1)[0].decode("utf-8-sig").strip('"')
                    try:
                        date.fromisoformat(candidate)
                    except ValueError:
                        continue
                    return candidate
                return None
            window = min(size, window * 2)


def _missing_trade_dates(csv_path: Path, trade_dates: list[str]) -> list[str]:
    """返回现有 CSV 最大交易日之后尚待更新的交易日。"""
    if not trade_dates:
        return []
    latest = _latest_csv_date(csv_path)
    if latest is None:
        # 首次运行没有可推导的历史起点，保持原有行为：只建立最新交易日增量。
        return [trade_dates[-1]]
    return [trade_date for trade_date in trade_dates if trade_date > latest]


def _date_range_summary(trade_dates: list[str]) -> dict[str, object]:
    return {
        "count": len(trade_dates),
        "start": trade_dates[0] if trade_dates else None,
        "end": trade_dates[-1] if trade_dates else None,
    }


def _normalize_index_codes(index_codes: list[str] | tuple[str, ...]) -> list[str]:
    normalized = [str(index_code).strip().upper() for index_code in index_codes]
    if not normalized or any(not index_code for index_code in normalized):
        raise ValueError("指数列表不能为空且不能包含空代码")
    if len(normalized) != len(set(normalized)):
        raise ValueError("指数列表不能包含重复代码")
    return normalized


def _update_index(
    client: EverydayUpdateClient,
    output_root: Path,
    index_code: str,
    trade_dates: list[str],
) -> dict[str, object]:
    print(f"[everydayupdate] 正在更新指数：{index_code}", flush=True)
    weights_csv_path = index_weights_artifact_path(output_root, index_code, "csv")
    weight_dates = _missing_trade_dates(weights_csv_path, trade_dates)
    weights_download = (
        download_index_weights(
            client,
            output_root,
            index_code,
            weight_dates[0],
            weight_dates[-1],
        )
        if weight_dates
        else {"raw_partitions": 0, "data_vol": 0, "skipped": 0}
    )
    weights_csv = update_index_weights_csv_range(
        output_root, index_code, weight_dates
    )
    weights_parquet = csv_to_index_weights_parquet(
        weights_csv_path,
        index_weights_artifact_path(output_root, index_code, "parquet"),
    )

    price_csv_path = index_price_artifact_path(output_root, index_code, "csv")
    price_dates = _missing_trade_dates(price_csv_path, trade_dates)
    price_download = (
        download_index_price(
            client,
            output_root,
            index_code,
            price_dates[0],
            price_dates[-1],
            1,
            DEFAULT_MAX_ESTIMATED_POINTS,
        )
        if price_dates
        else {
            "raw_partitions": 0,
            "data_vol": 0,
            "estimated_points": 0,
            "skipped": 0,
        }
    )
    price_csv = update_index_price_csv_range(output_root, index_code, price_dates)
    price_parquet = csv_to_index_price_parquet(
        price_csv_path,
        index_price_artifact_path(output_root, index_code, "parquet"),
    )
    return {
        "weights": {
            "update_range": _date_range_summary(weight_dates),
            "download": weights_download,
            "csv": weights_csv,
            "parquet": weights_parquet,
        },
        "price": {
            "update_range": _date_range_summary(price_dates),
            "download": price_download,
            "csv": price_csv,
            "parquet": price_parquet,
        },
    }


def run_everyday_update(
    client: EverydayUpdateClient,
    output_root: Path,
    as_of: str,
    index_codes: list[str] | tuple[str, ...] | None = None,
    workers: int = DEFAULT_WORKERS,
) -> dict[str, object]:
    """执行交易日历、证券池/指数数据和股票行情的完整日更新。"""
    resolved_index_codes = _normalize_index_codes(
        INDEX_CODES if index_codes is None else index_codes
    )
    print(f"[everydayupdate] 目标日期：{as_of}", flush=True)

    print("[everydayupdate] 第 1/3 步：更新交易日历", flush=True)
    calendar_added = update_calendar(client, output_root, as_of)
    calendar_dir = output_root / "calendar"
    calendar_parquet = csv_to_flat_parquet(
        calendar_dir / CALENDAR_CSV_FILENAME,
        calendar_dir / CALENDAR_PARQUET_FILENAME,
        "calendar_parquet",
    )
    trade_dates = [
        trade_date
        for trade_date in read_calendar_dates(calendar_dir / CALENDAR_CSV_FILENAME)
        if trade_date <= as_of
    ]
    if not trade_dates:
        raise ValueError(f"交易日历中没有不晚于 {as_of} 的交易日")
    latest_trade_date = trade_dates[-1]

    print("[everydayupdate] 第 2/3 步：更新股票池、指数权重和指数价格", flush=True)
    universe_download = run_universe_download(
        client, output_root, as_of=latest_trade_date
    )
    universe_csv = update_universe_csv(output_root, latest_trade_date)
    universe_parquet = csv_to_flat_parquet(
        existing_universe_path(output_root),
        output_root / "universe" / "a_share.parquet",
        "universe_parquet",
    )
    indices = {
        index_code: _update_index(client, output_root, index_code, trade_dates)
        for index_code in resolved_index_codes
    }

    print("[everydayupdate] 第 3/3 步：更新回测行情和未复权行情", flush=True)
    universe_path = existing_universe_path(output_root)
    market_dir = output_root / MARKET_DATA_DIR
    market_csv_path = market_dir / MARKET_DATA_CSV_FILENAME
    market_dates = _missing_trade_dates(market_csv_path, trade_dates)
    market_download = (
        download_market_data(
            client,
            output_root,
            universe_path,
            market_dates[0],
            market_dates[-1],
            DEFAULT_SYMBOLS_PER_REQUEST,
            1,
            DEFAULT_MAX_ESTIMATED_POINTS,
        )
        if market_dates
        else {}
    )
    market_csv = update_daily_csv_range(
        output_root, market_dates, workers, universe_path
    )
    market_parquet = csv_to_parquet(
        market_csv_path,
        market_dir / MARKET_DATA_PARQUET_FILENAME,
    )
    unadjusted_price_dir = output_root / UNADJUSTED_PRICE_DIR
    unadjusted_price_csv_path = (
        unadjusted_price_dir / UNADJUSTED_PRICE_CSV_FILENAME
    )
    unadjusted_price_dates = _missing_trade_dates(
        unadjusted_price_csv_path, trade_dates
    )
    unadjusted_price_download = (
        download_unadjusted_price(
            client,
            output_root,
            universe_path,
            unadjusted_price_dates[0],
            unadjusted_price_dates[-1],
            DEFAULT_SYMBOLS_PER_REQUEST,
            1,
            DEFAULT_MAX_ESTIMATED_POINTS,
        )
        if unadjusted_price_dates
        else {}
    )
    unadjusted_price_csv = update_price_csv_range(
        output_root, unadjusted_price_dates, workers, universe_path
    )
    unadjusted_price_parquet = csv_to_unadjusted_price_parquet(
        unadjusted_price_csv_path,
        unadjusted_price_dir / UNADJUSTED_PRICE_PARQUET_FILENAME,
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
            "indices": indices,
        },
        "market_data": {
            "adjustment": "hfq",
            "update_range": _date_range_summary(market_dates),
            "download": market_download,
            "csv": market_csv,
            "parquet": market_parquet,
        },
        "unadjusted_price": {
            "adjustment": "none",
            "update_range": _date_range_summary(unadjusted_price_dates),
            "download": unadjusted_price_download,
            "csv": unadjusted_price_csv,
            "parquet": unadjusted_price_parquet,
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
        "--index",
        dest="index_codes",
        action="append",
        help="临时覆盖脚本内 INDEX_CODES；可重复传入多个指数代码",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summary = run_everyday_update(
        IFindClient.from_environment(),
        args.output_root,
        args.as_of or default_update_as_of(),
        args.index_codes,
        args.workers,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
