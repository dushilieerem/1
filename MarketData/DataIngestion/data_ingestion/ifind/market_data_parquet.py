"""将完整日频行情 CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def csv_to_parquet(csv_path: Path, parquet_path: Path) -> dict[str, int]:
    import pyarrow.csv
    import pyarrow.parquet

    table = pyarrow.csv.read_csv(csv_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = parquet_path.with_suffix(".parquet.tmp")
    pyarrow.parquet.write_table(table, temporary_path, compression="zstd")
    temporary_path.replace(parquet_path)
    return {"rows": table.num_rows, "columns": table.num_columns}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[3] / "sources" / "ifind")
    args = parser.parse_args()
    print(json.dumps(csv_to_parquet(args.output_root / "daily.csv", args.output_root / "daily.parquet"), ensure_ascii=False))


if __name__ == "__main__":
    main()
