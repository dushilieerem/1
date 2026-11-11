# -*- coding: utf-8 -*-
"""合并机构端 doc_extract 分批 CSV，按 (doc_id, field_key) 去重并输出 pending SQL。"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_inst_gov_fields import sql_row  # noqa: E402

COLUMNS = [
    "symbol",
    "field_key",
    "field_label",
    "value_text",
    "value_num",
    "unit",
    "report_period",
    "page_no",
    "quote",
    "doc_id",
    "pdf_sha256",
    "source_url",
    "available_time",
    "extractor_version",
    "confidence",
    "review_status",
    "reviewed_by",
    "reviewed_at",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--out-dir", default="backend/output/inst_doc_extract_combined")
    args = parser.parse_args()

    frames = [pd.read_csv(path) for path in args.inputs]
    df = pd.concat(frames, ignore_index=True)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[COLUMNS]
    df = df.drop_duplicates(subset=["doc_id", "field_key"], keep="first")
    df = df.sort_values(["symbol", "report_period", "field_key"])

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "combined_pending.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    sql_path = out / "combined_pending.sql"
    with sql_path.open("w", encoding="utf-8") as fh:
        fh.write("-- 机构端 doc_extract 合并结果，review_status=pending，复核后再改 approved\n")
        for row in df.to_dict("records"):
            fh.write(sql_row(row) + "\n")

    counts = df.groupby("field_key").size().sort_index()
    print(f"rows={len(df)} csv={csv_path} sql={sql_path}")
    for key, count in counts.items():
        print(f"{key}={count}")


if __name__ == "__main__":
    main()
