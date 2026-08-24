"""将全 A 证券池 CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_ingestion.ifind.common.parquet import csv_to_flat_parquet
from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.universe.pipeline import existing_universe_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    path = args.output_root / "universe"
    csv_path = existing_universe_path(args.output_root)
    print(json.dumps(csv_to_flat_parquet(csv_path, path / "a_share.parquet", "universe_parquet"), ensure_ascii=False))


if __name__ == "__main__":
    main()
