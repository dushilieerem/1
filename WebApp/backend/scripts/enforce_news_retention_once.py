# -*- coding: utf-8 -*-
"""One-shot: FIFO 裁剪资讯上限（要闻流/电报/公告）。"""
from __future__ import annotations

from services.core.db import get_conn
from services.news.news_store import (
    NEWS_CAP_ANNOUNCE,
    NEWS_CAP_FEED,
    NEWS_CAP_FLASH,
    ensure_news_schema,
    enforce_news_retention,
)


def _counts() -> dict[str, int]:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM news_items").fetchone()["n"]
        flash = conn.execute(
            "SELECT COUNT(*) AS n FROM news_items WHERE is_flash = TRUE"
        ).fetchone()["n"]
        announce = conn.execute(
            "SELECT COUNT(*) AS n FROM news_items WHERE category = 'announce'"
        ).fetchone()["n"]
    return {
        "feed": int(total),
        "flash": int(flash),
        "announce": int(announce),
    }


def main() -> None:
    ensure_news_schema()
    before = _counts()
    print(
        f"before: feed={before['feed']}/{NEWS_CAP_FEED} "
        f"flash={before['flash']}/{NEWS_CAP_FLASH} "
        f"announce={before['announce']}/{NEWS_CAP_ANNOUNCE}"
    )
    stats = enforce_news_retention()
    after = _counts()
    print("pruned:", stats)
    print(
        f"after:  feed={after['feed']}/{NEWS_CAP_FEED} "
        f"flash={after['flash']}/{NEWS_CAP_FLASH} "
        f"announce={after['announce']}/{NEWS_CAP_ANNOUNCE}"
    )


if __name__ == "__main__":
    main()
