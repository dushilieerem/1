"""将全 A 统一交易日历 CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_ingestion.ifind.calendar.pipeline import CALENDAR_CSV_FILENAME, CALENDAR_PARQUET_FILENAME
from data_ingestion.ifind.common.parquet import csv_to_flat_parquet
from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    path = args.output_root / "calendar"
    print(json.dumps(csv_to_flat_parquet(path / CALENDAR_CSV_FILENAME, path / CALENDAR_PARQUET_FILENAME, "calendar_parquet"), ensure_ascii=False))


if __name__ == "__main__":
    main()
