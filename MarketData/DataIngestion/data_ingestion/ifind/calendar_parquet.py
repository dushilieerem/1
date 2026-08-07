"""将全 A 统一交易日历 CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_ingestion.ifind.flat_parquet import csv_to_flat_parquet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[3] / "sources" / "ifind")
    args = parser.parse_args()
    path = args.output_root / "calendar"
    print(json.dumps(csv_to_flat_parquet(path / "ALL_A.csv", path / "ALL_A.parquet", "calendar_parquet"), ensure_ascii=False))


if __name__ == "__main__":
    main()
