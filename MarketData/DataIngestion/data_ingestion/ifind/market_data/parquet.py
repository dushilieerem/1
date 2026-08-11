"""将完整日频行情 CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.market_data.csv import OUTPUT_DIR, OUTPUT_FILENAME

OUTPUT_PARQUET_FILENAME = "market_data_hfq.parquet"


def csv_to_parquet(csv_path: Path, parquet_path: Path, label: str = "market_data_parquet") -> dict[str, int]:
    import pandas as pd

    print(f"[{label}] 1/2：正在读取 {csv_path}", flush=True)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        symbols = next(reader)
        fields = next(reader)
    if len(symbols) != len(fields) or not symbols:
        raise ValueError(f"两级表头列数不一致：{csv_path}")
    flat_columns = ["date", *(f"{symbol}__{field}" for symbol, field in zip(symbols[1:], fields[1:], strict=True))]
    frame = pd.read_csv(csv_path, header=None, skiprows=2, names=flat_columns, index_col=0, low_memory=False)
    frame.columns = pd.MultiIndex.from_arrays((symbols[1:], fields[1:]))
    frame.index.name = "date"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = parquet_path.with_suffix(".parquet.tmp")
    print(f"[{label}] 2/2：正在写入 {parquet_path}", flush=True)
    frame.to_parquet(temporary_path, engine="pyarrow", compression="zstd")
    temporary_path.replace(parquet_path)
    print(f"[{label}] 已完成：{len(frame)} 行，写入 {parquet_path}", flush=True)
    return {"rows": len(frame), "columns": len(frame.columns)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    output_dir = args.output_root / OUTPUT_DIR
    print(json.dumps(csv_to_parquet(output_dir / OUTPUT_FILENAME, output_dir / OUTPUT_PARQUET_FILENAME), ensure_ascii=False))


if __name__ == "__main__":
    main()
