"""Fetch public announcement/research *titles and links* for the Invest universe.

Only metadata is stored (title, source, time, URL) — no article body.  This is
not a substitute for a licensed news feed; verify public-display terms before
launch.  "要闻" remains demo seed data.

Usage:
  conda run -n svquant python scripts/fetch_news.py --db data/invest.db --codes all
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seed import DB_PATH  # noqa: E402

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
}
ANN = "https://np-anotice-stock.eastmoney.com/api/security/ann"
REPORT = "https://reportapi.eastmoney.com/report/list"
HEADLINE = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"


def get_json(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def announcement_rows(code: str) -> list[tuple]:
    data = get_json(ANN, {
        "sr": -1, "page_size": 3, "page_index": 1, "ann_type": "A",
        "client_source": "web", "stock_list": code,
    })
    out = []
    for item in ((data.get("data") or {}).get("list") or []):
        art = item.get("art_code")
        if not art:
            continue
        when = (item.get("display_time") or item.get("notice_date") or "")[:16]
        column = ((item.get("columns") or [{}])[0]).get("column_name") or "公告"
        out.append((
            f"ann-{art}", item.get("title") or "公告", column, "东方财富",
            when, "announcement", code, None,
            f"https://data.eastmoney.com/notices/detail/{code}/{art}.html",
        ))
    return out


def report_rows(code: str) -> list[tuple]:
    data = get_json(REPORT, {
        "industryCode": "*", "pageSize": 3, "industry": "*", "rating": "",
        "ratingChange": "", "beginTime": "2026-01-01", "endTime": "2026-12-31",
        "pageNo": 1, "fields": "", "qType": 0, "orgCode": "", "code": code,
        "rcode": "", "p": 1, "pageNum": 1,
    })
    out = []
    for item in (data.get("data") or []):
        info = item.get("infoCode")
        if not info:
            continue
        when = (item.get("publishDate") or "")[:16]
        org = item.get("orgSName") or item.get("orgName") or "机构"
        rating = item.get("emRatingName") or item.get("sRatingName") or ""
        summary = " · ".join(x for x in (org, rating) if x)
        out.append((
            f"rep-{info}", item.get("title") or "研报", summary, org,
            when, "report", code, None,
            f"https://data.eastmoney.com/report/zw_stock.jshtml?infocode={info}",
        ))
    return out


def headline_rows() -> list[tuple]:
    data = get_json(HEADLINE, {
        "client": "web", "biz": "web_news_col", "column": 350, "order": 1,
        "needInteractData": 0, "page_index": 1, "page_size": 20, "req_trace": 1,
    })
    out = []
    for item in ((data.get("data") or {}).get("list") or []):
        code = item.get("code")
        if not code:
            continue
        out.append((
            f"news-{code}", item.get("title") or "要闻", "", item.get("mediaName") or "东方财富",
            (item.get("showTime") or "")[:16], "news", None, None,
            item.get("uniqueUrl") or item.get("url") or "",
        ))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None)
    parser.add_argument("--codes", default="all")
    args = parser.parse_args()
    path = Path(args.db) if args.db else DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    if args.codes == "all":
        codes = [r["code"] for r in conn.execute("SELECT code FROM stocks WHERE asset='stock'").fetchall()]
    else:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    ann = rep = headline = 0
    for code in codes:
        try:
            rows = announcement_rows(code)
            conn.executemany("INSERT OR REPLACE INTO news VALUES (?,?,?,?,?,?,?,?,?)", rows)
            ann += len(rows)
        except Exception as exc:
            print(f"[{code}] announcement failed: {exc}")
        try:
            rows = report_rows(code)
            conn.executemany("INSERT OR REPLACE INTO news VALUES (?,?,?,?,?,?,?,?,?)", rows)
            rep += len(rows)
        except Exception as exc:
            print(f"[{code}] report failed: {exc}")
    try:
        rows = headline_rows()
        conn.executemany("INSERT OR REPLACE INTO news VALUES (?,?,?,?,?,?,?,?,?)", rows)
        conn.execute("DELETE FROM news WHERE kind='news' AND id NOT LIKE 'news-%'")
        headline = len(rows)
    except Exception as exc:
        print(f"[headline] failed: {exc}")
    conn.commit()
    conn.close()
    print(f"done announcements={ann} reports={rep} headlines={headline}")


if __name__ == "__main__":
    main()
