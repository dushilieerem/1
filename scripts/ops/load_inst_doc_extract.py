# -*- coding: utf-8 -*-
"""把 doc_extract 抽取 CSV 写入 PostgreSQL。

默认只允许测试/开发库（*_test / *_dev / *_ci）；生产必须显式 --allow-production。
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

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


def _db_name(dsn: str) -> str:
    return urlsplit(dsn).path.lstrip("/")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--review-status", default="pending")
    args = parser.parse_args()

    dsn = str(args.dsn or "").strip()
    if not dsn:
        raise SystemExit("missing DATABASE_URL or --dsn")
    name = _db_name(dsn)
    safe = name.endswith("_test") or name.endswith("_dev") or name.endswith("_ci") or name == "svquant_test"
    if not safe and not args.allow_production:
        raise SystemExit(f"refusing to write non-test database: {name}")

    rows = list(csv.DictReader(Path(args.csv).open(encoding="utf-8-sig", newline="")))
    if not rows:
        raise SystemExit("empty csv")
    for row in rows:
        row["review_status"] = args.review_status

    sql = f"""
        INSERT INTO svquant.doc_extract ({', '.join(COLUMNS)})
        VALUES ({', '.join(['%s'] * len(COLUMNS))})
        ON CONFLICT (doc_id, field_key) DO UPDATE SET
          value_text=EXCLUDED.value_text,
          value_num=EXCLUDED.value_num,
          unit=EXCLUDED.unit,
          report_period=EXCLUDED.report_period,
          page_no=EXCLUDED.page_no,
          quote=EXCLUDED.quote,
          pdf_sha256=EXCLUDED.pdf_sha256,
          source_url=EXCLUDED.source_url,
          available_time=EXCLUDED.available_time,
          extractor_version=EXCLUDED.extractor_version,
          confidence=EXCLUDED.confidence,
          review_status=EXCLUDED.review_status,
          reviewed_by=EXCLUDED.reviewed_by,
          reviewed_at=EXCLUDED.reviewed_at
    """
    values = [tuple(row.get(col) or None for col in COLUMNS) for row in rows]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, values)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM svquant.doc_extract").fetchone()[0]
    print(f"loaded={len(rows)} db={name} total={count}")


if __name__ == "__main__":
    main()
