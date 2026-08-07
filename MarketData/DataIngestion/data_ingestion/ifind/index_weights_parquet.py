"""将 iFinD 指数成分股权重 CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_ingestion.ifind.flat_parquet import csv_to_flat_parquet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default="000300.SH")
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[3] / "sources" / "ifind")
    args = parser.parse_args()
    folder = args.output_root / "index_weights"
    print(json.dumps(csv_to_flat_parquet(folder / f"{args.index}.csv", folder / f"{args.index}.parquet", "index_weights_parquet"), ensure_ascii=False))


if __name__ == "__main__":
    main()
