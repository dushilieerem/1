# -*- coding: utf-8 -*-
"""One-shot: 纠正东财研报 published_at（曾因 ".000" 毫秒后缀解析失败被兜底为抓取时间）。"""
from __future__ import annotations

from services.core.db import get_conn
from services.news.news_ingest import backfill_eastmoney_research_dates
from services.news.news_store import ensure_news_schema


def _snapshot() -> tuple[int, int, str, str]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (
                     WHERE published_at <> date_trunc('second', published_at)
                   ) AS with_microsec,
                   MIN(published_at) AS min_pub,
                   MAX(published_at) AS max_pub
            FROM news_items
            WHERE source = 'eastmoney' AND category = 'research'
            """
        ).fetchone()
    return (
        int(row["total"]),
        int(row["with_microsec"]),
        str(row["min_pub"]),
        str(row["max_pub"]),
    )


def main() -> None:
    ensure_news_schema()
    total, micro, mn, mx = _snapshot()
    print(f"before: total={total} 带微秒(兜底值)={micro}")
    print(f"        pub 范围 {mn} ~ {mx}")

    stats = backfill_eastmoney_research_dates()
    print(f"backfill: {stats}")

    total, micro, mn, mx = _snapshot()
    print(f"after : total={total} 带微秒(兜底值)={micro}")
    print(f"        pub 范围 {mn} ~ {mx}")

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT title, published_at, created_at
            FROM news_items
            WHERE source = 'eastmoney' AND category = 'research'
            ORDER BY published_at DESC, id DESC
            LIMIT 8
            """
        ).fetchall()
    print("--- samples (published_at 最新 8 条) ---")
    for r in rows:
        print(f"{r['published_at']} | created={r['created_at']} | {(r['title'] or '')[:44]}")


if __name__ == "__main__":
    main()
