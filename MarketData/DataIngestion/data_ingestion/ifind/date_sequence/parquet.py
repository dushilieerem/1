"""将完整日期序列 CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.market_data.parquet import csv_to_parquet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    print(json.dumps(csv_to_parquet(args.output_root / "date_sequence.csv", args.output_root / "date_sequence.parquet", "date_sequence_parquet"), ensure_ascii=False))


if __name__ == "__main__":
    main()
