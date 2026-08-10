"""将日期 × 股票的指数权重 CSV 转为同结构 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT


def csv_to_index_weights_parquet(csv_path: Path, parquet_path: Path) -> dict[str, int]:
    import pandas as pd

    print(f"[index_weights_parquet] 1/2：正在读取 {csv_path}", flush=True)
    frame = pd.read_csv(csv_path, index_col="date", parse_dates=["date"])
    frame.index.name = "date"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = parquet_path.with_suffix(".parquet.tmp")
    print(f"[index_weights_parquet] 2/2：正在写入 {parquet_path}", flush=True)
    frame.to_parquet(temporary_path, engine="pyarrow", compression="zstd")
    temporary_path.replace(parquet_path)
    print(f"[index_weights_parquet] 已完成：{len(frame)} 行，写入 {parquet_path}", flush=True)
    return {"rows": len(frame), "columns": len(frame.columns)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default="000300.SH")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    folder = args.output_root / "index_weights"
    print(json.dumps(csv_to_index_weights_parquet(folder / f"{args.index}.csv", folder / f"{args.index}.parquet"), ensure_ascii=False))


if __name__ == "__main__":
    main()
