"""将完整日频行情 CSV 转为 Parquet，不调用 iFinD。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.market_data.csv import OUTPUT_DIR, OUTPUT_FILENAME

OUTPUT_PARQUET_FILENAME = "market_data_hfq.parquet"
DEFAULT_CHUNK_ROWS = 64


def csv_to_parquet(
    csv_path: Path,
    parquet_path: Path,
    label: str = "market_data_parquet",
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> dict[str, int]:
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    if chunk_rows <= 0:
        raise ValueError("chunk_rows 必须为正整数")

    print(f"[{label}] 1/2：正在读取 {csv_path}", flush=True)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        symbols = next(reader)
        fields = next(reader)
    if len(symbols) != len(fields) or not symbols:
        raise ValueError(f"两级表头列数不一致：{csv_path}")
    flat_columns = ["date", *(f"{symbol}__{field}" for symbol, field in zip(symbols[1:], fields[1:], strict=True))]
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = parquet_path.with_suffix(".parquet.tmp")
    value_dtypes = {column: "float64" for column in flat_columns[1:]}
    column_index = pd.MultiIndex.from_arrays((symbols[1:], fields[1:]))
    writer = None
    rows = 0
    print(f"[{label}] 2/2：正在分块写入 {parquet_path}（每块 {chunk_rows} 行）", flush=True)
    try:
        chunks = pd.read_csv(
            csv_path,
            header=None,
            skiprows=2,
            names=flat_columns,
            index_col=0,
            dtype=value_dtypes,
            chunksize=chunk_rows,
            low_memory=False,
        )
        for frame in chunks:
            frame.columns = column_index
            frame.index.name = "date"
            table = pa.Table.from_pandas(frame, preserve_index=True)
            if writer is None:
                writer = pq.ParquetWriter(temporary_path, table.schema, compression="zstd")
            elif table.schema != writer.schema:
                raise ValueError("CSV 分块推导出的 Parquet schema 不一致")
            writer.write_table(table)
            rows += len(frame)

        if writer is None:
            empty = pd.DataFrame(index=pd.Index([], name="date"), columns=column_index, dtype="float64")
            table = pa.Table.from_pandas(empty, preserve_index=True)
            writer = pq.ParquetWriter(temporary_path, table.schema, compression="zstd")
        writer.close()
        writer = None
        temporary_path.replace(parquet_path)
    except Exception:
        if writer is not None:
            writer.close()
        temporary_path.unlink(missing_ok=True)
        raise

    print(f"[{label}] 已完成：{rows} 行，写入 {parquet_path}", flush=True)
    return {"rows": rows, "columns": len(column_index)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--chunk-rows", type=int, default=DEFAULT_CHUNK_ROWS)
    args = parser.parse_args()
    output_dir = args.output_root / OUTPUT_DIR
    print(
        json.dumps(
            csv_to_parquet(
                output_dir / OUTPUT_FILENAME,
                output_dir / OUTPUT_PARQUET_FILENAME,
                chunk_rows=args.chunk_rows,
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
