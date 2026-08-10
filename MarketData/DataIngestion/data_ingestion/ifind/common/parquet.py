"""普通单层表头 CSV 的 Parquet 转换工具。"""

from __future__ import annotations

from pathlib import Path


def csv_to_flat_parquet(csv_path: Path, parquet_path: Path, label: str) -> dict[str, int]:
    import pandas as pd

    print(f"[{label}] 1/2：正在读取 {csv_path}", flush=True)
    frame = pd.read_csv(csv_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = parquet_path.with_suffix(".parquet.tmp")
    print(f"[{label}] 2/2：正在写入 {parquet_path}", flush=True)
    frame.to_parquet(temporary_path, engine="pyarrow", compression="zstd", index=False)
    temporary_path.replace(parquet_path)
    print(f"[{label}] 已完成：{len(frame)} 行，写入 {parquet_path}", flush=True)
    return {"rows": len(frame), "columns": len(frame.columns)}
