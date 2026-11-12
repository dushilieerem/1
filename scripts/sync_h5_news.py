#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把主站 news_items 同步到 H5 的 doc_item（资讯视图）。

H5 `/api/invest/news` 读 doc_item；公告由 fetch_financials 写入，
要闻/研报需要从主站资讯同步。

  DATABASE_URL=... /home/dev01/program/anaconda3/bin/python scripts/sync_h5_news.py --limit 2000
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.invest.schema import ensure_invest_schema  # noqa: E402


def _hash(*parts: object) -> str:
    raw = "|".join(str(x or "") for x in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=2000)
    args = ap.parse_args()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("需要 DATABASE_URL")
    ensure_invest_schema()
    inserted = 0
    with psycopg.connect(url, row_factory=psycopg.rows.dict_row) as conn:
        rows = conn.execute(
            """
            SELECT title, summary, url, source, published_at, category, symbols
              FROM news_items
             WHERE published_at IS NOT NULL
             ORDER BY published_at DESC
             LIMIT %s
            """,
            (max(1, min(5000, args.limit)),),
        ).fetchall()
        for row in rows:
            category = str(row.get("category") or "")
            if category in {"announce", "announcement"}:
                continue  # 公告由 fetch_financials 单独写入
            doc_type = "research" if category == "research" else "news"
            symbols = row.get("symbols") or []
            symbol = None
            if isinstance(symbols, list) and symbols:
                symbol = str(symbols[0]).upper()
            content_hash = _hash(row.get("source"), row.get("url"), row.get("title"), row.get("published_at"))
            cur = conn.execute(
                """
                INSERT INTO doc_item
                  (doc_type, symbol, title, publish_at, url, source, content_hash, summary, as_of)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::date)
                ON CONFLICT (source, content_hash) DO NOTHING
                """,
                (
                    doc_type,
                    symbol,
                    str(row.get("title") or ""),
                    row.get("published_at"),
                    row.get("url"),
                    str(row.get("source") or "svquant"),
                    content_hash,
                    str(row.get("summary") or "")[:2000],
                    row.get("published_at"),
                ),
            )
            inserted += cur.rowcount or 0
        conn.commit()
    print(f"[sync_h5_news] scanned={len(rows)} inserted={inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
