# -*- coding: utf-8 -*-
"""One-shot: backfill news tags after dict deepen; print coverage."""
from __future__ import annotations

from services.db import get_conn
from services.news_ingest import backfill_news_tags
from services.news_store import ensure_news_schema
from services.news_tag_dict import dict_snapshot


def main() -> None:
    ensure_news_schema()
    snap = dict_snapshot()
    print("themes", len(snap["themes"]), snap["themes"])
    print("industries", len(snap["industries"]))

    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM news_items").fetchone()["n"]
        tagged_before = conn.execute(
            """
            SELECT COUNT(*) AS n FROM news_items
            WHERE jsonb_array_length(themes) > 0
               OR jsonb_array_length(industries) > 0
            """
        ).fetchone()["n"]
        empty_before = conn.execute(
            """
            SELECT COUNT(*) AS n FROM news_items
            WHERE themes = '[]'::jsonb AND industries = '[]'::jsonb
            """
        ).fetchone()["n"]
    print(f"before: total={total} tagged={tagged_before} empty={empty_before}")

    n = backfill_news_tags(limit=500)
    print(f"retagged_rows={n}")

    with get_conn() as conn:
        tagged_after = conn.execute(
            """
            SELECT COUNT(*) AS n FROM news_items
            WHERE jsonb_array_length(themes) > 0
               OR jsonb_array_length(industries) > 0
            """
        ).fetchone()["n"]
        empty_after = conn.execute(
            """
            SELECT COUNT(*) AS n FROM news_items
            WHERE themes = '[]'::jsonb AND industries = '[]'::jsonb
            """
        ).fetchone()["n"]
        rows = conn.execute(
            """
            SELECT title, themes, industries FROM news_items
            WHERE jsonb_array_length(themes) > 0
            ORDER BY published_at DESC NULLS LAST, id DESC
            LIMIT 12
            """
        ).fetchall()
    print(f"after: tagged={tagged_after} empty={empty_after}")
    print("--- samples ---")
    for r in rows:
        title = (r["title"] or "")[:60]
        print(r["themes"], "|", r["industries"], "|", title)


if __name__ == "__main__":
    main()
