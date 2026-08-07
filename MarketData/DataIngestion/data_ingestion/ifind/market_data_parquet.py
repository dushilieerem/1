"""将完整日频行情 CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_ingestion.ifind.market_data_download import ADJUSTMENTS


def csv_to_parquet(csv_path: Path, parquet_path: Path, label: str = "market_data_parquet") -> dict[str, int]:
    import pandas as pd

    print(f"[{label}] 1/2：正在读取 {csv_path}", flush=True)
    frame = pd.read_csv(csv_path, header=[0, 1], index_col=0)
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
    parser.add_argument("--output-root", type=Path, default=Path(__file__).resolve().parents[3] / "sources" / "ifind")
    parser.add_argument("--adjustment", choices=ADJUSTMENTS, default="hfq", help="价格复权方式：hfq=后复权，qfq=前复权，none=不复权")
    args = parser.parse_args()
    stem = f"market_data_{args.adjustment}"
    print(json.dumps(csv_to_parquet(args.output_root / f"{stem}.csv", args.output_root / f"{stem}.parquet"), ensure_ascii=False))


if __name__ == "__main__":
    main()
