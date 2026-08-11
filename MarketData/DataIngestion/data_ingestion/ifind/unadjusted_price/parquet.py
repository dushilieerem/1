"""将完整未复权 OHLC CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.market_data.parquet import csv_to_parquet as csv_to_wide_parquet
from data_ingestion.ifind.unadjusted_price.csv import OUTPUT_DIR, OUTPUT_FILENAME

OUTPUT_PARQUET_FILENAME = "unadjusted_price.parquet"


def csv_to_parquet(csv_path: Path, parquet_path: Path) -> dict[str, int]:
    return csv_to_wide_parquet(csv_path, parquet_path, "unadjusted_price_parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    output_dir = args.output_root / OUTPUT_DIR
    print(json.dumps(csv_to_parquet(output_dir / OUTPUT_FILENAME, output_dir / OUTPUT_PARQUET_FILENAME), ensure_ascii=False))


if __name__ == "__main__":
    main()
