#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 PostgreSQL 服务层同步到 Invest H5 的 SQLite 读取缓存。

架构口径：PG 是数据汇总层；`invest-api` 的 SQLite 只是移动端读取缓存，
可以随时由本脚本重建。用户数据（watchlist/portfolio/risk/events）不被覆盖。

运行环境：base（pyarrow 不需要；需要 psycopg）。
  /home/dev01/program/anaconda3/bin/python scripts/sync_invest_sqlite.py
  /home/dev01/program/anaconda3/bin/python scripts/sync_invest_sqlite.py --limit-symbols 800
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.core.env_config import env  # noqa: E402

DEFAULT_DB = ROOT / "invest-api" / "data" / "invest.dev.db"
TODAY = date.today().isoformat()
# PG A 股 universe 不含 ETF；手机端示例组合含 510300，用腾讯公开行情补一个最小快照。
ETF_CODES = {"510300": "沪深300ETF", "510500": "中证500ETF", "512880": "证券ETF"}
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}


def fetch_etf_bars(code: str) -> list[dict[str, Any]]:
    prefix = "sh" if code.startswith("5") else "sz"
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    try:
        data = requests.get(url, params={"param": f"{prefix}{code},day,,,20,qfq"}, headers=HEADERS, timeout=20).json()
        node = ((data.get("data") or {}).get(f"{prefix}{code}") or {})
        rows = node.get("qfqday") or node.get("day") or []
    except Exception:
        return []
    out = []
    for r in rows:
        if len(r) < 6:
            continue
        try:
            out.append(
                {
                    "date": str(r[0])[:10],
                    "open": float(r[1]),
                    "close": float(r[2]),
                    "high": float(r[3]),
                    "low": float(r[4]),
                    "volume": float(r[5]),
                    "amount": float(r[5]) * float(r[2]) * 100,
                }
            )
        except (TypeError, ValueError):
            continue
    return out


def pg_url() -> str:
    url = env("DATABASE_URL", "") or ""
    if not url:
        raise SystemExit("backend/.env 缺少 DATABASE_URL")
    return url


def bare(symbol: str) -> str:
    return str(symbol).split(".")[0]


def period_label(report_date: Any) -> str:
    text = str(report_date)[:10]
    try:
        year, month, _ = text.split("-")
        q = (int(month) - 1) // 3 + 1
        return f"{year}Q{q}"
    except Exception:
        return text


def yi(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value) / 1e8, 2)


def pct100(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value) * 100, 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--limit-symbols", type=int, default=500, help="写入 bars/valuations 的标的数")
    ap.add_argument("--bar-days", type=int, default=750)
    ap.add_argument("--news-limit", type=int, default=300)
    args = ap.parse_args()
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(pg_url()) as pg:
        pg.row_factory = psycopg.rows.dict_row
        latest_date = pg.execute("SELECT MAX(trade_date) AS d FROM md_daily_bar").fetchone()["d"]
        if not latest_date:
            raise SystemExit("PG 中没有 md_daily_bar，先运行 etl_marketdata.py")

        # 现有 SQLite 标的 + 机构公司池 + 市值最大的 N 只
        existing: set[str] = set()
        if db_path.exists():
            try:
                conn0 = sqlite3.connect(db_path)
                # 只把“已有日线”的标的视为需要保留的池，避免全市场 stocks 把 limit 撑满。
                existing = {str(r[0]) for r in conn0.execute("SELECT DISTINCT code FROM bars").fetchall()}
                conn0.close()
            except Exception:
                existing = set()
        pool = pg.execute(
            """
            SELECT s.symbol, s.name, s.board,
                   COALESCE(ind.name, i.industry_code) AS industry_code,
                   v.pe_ttm, v.pb_mrq, v.dividend_yield_ttm, v.float_mv, v.total_mv
              FROM ref_security s
              LEFT JOIN LATERAL (
                SELECT industry_code FROM ref_security_industry x
                 WHERE x.symbol=s.symbol AND x.level=1 ORDER BY effective_from DESC LIMIT 1
              ) i ON TRUE
              LEFT JOIN LATERAL (
                SELECT raw->>'INDUSTRY_NAME' AS name FROM fin_income_statement f
                 WHERE f.symbol=s.symbol AND f.raw ? 'INDUSTRY_NAME'
                 ORDER BY f.report_date DESC LIMIT 1
              ) ind ON TRUE
              LEFT JOIN LATERAL (
                SELECT pe_ttm, pb_mrq, dividend_yield_ttm, float_mv, total_mv
                  FROM md_valuation_daily v WHERE v.symbol=s.symbol
                 ORDER BY trade_date DESC LIMIT 1
              ) v ON TRUE
             WHERE s.status='listed'
             ORDER BY v.float_mv DESC NULLS LAST, s.symbol
            """
        ).fetchall()
        all_codes = {bare(r["symbol"]) for r in pool}
        selected = [r for r in pool if bare(r["symbol"]) in existing][: args.limit_symbols]
        selected_codes = {bare(r["symbol"]) for r in selected}
        for r in pool:
            if len(selected) >= args.limit_symbols:
                break
            if bare(r["symbol"]) not in selected_codes:
                selected.append(r)
                selected_codes.add(bare(r["symbol"]))
        # 机构公司池必须包含
        inst = pg.execute("SELECT DISTINCT symbol FROM inst_company WHERE market='CN'").fetchall()
        for r in inst:
            code = bare(r["symbol"])
            if code not in selected_codes and code in all_codes:
                row = next((x for x in pool if bare(x["symbol"]) == code), None)
                if row:
                    selected.append(row)
                    selected_codes.add(code)

        # 最新行情与上一日
        quote_rows = pg.execute(
            """
            SELECT n.symbol, n.trade_date, n.open, n.high, n.low, n.close, n.pre_close,
                   COALESCE(n.volume, h.volume) AS volume,
                   COALESCE(n.amount, h.amount) AS amount,
                   COALESCE(n.turnover, h.turnover) AS turnover
              FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date DESC) AS rn
                  FROM md_daily_bar WHERE adjust='none'
              ) n
              LEFT JOIN md_daily_bar h
                ON h.symbol=n.symbol AND h.trade_date=n.trade_date AND h.adjust='hfq'
             WHERE n.rn <= 2
            """
        ).fetchall()
        quotes: dict[str, list[dict[str, Any]]] = {}
        for r in quote_rows:
            quotes.setdefault(bare(r["symbol"]), []).append(r)

        stock_rows = []
        etf_bars: dict[str, list[dict[str, Any]]] = {}
        for r in pool:
            code = bare(r["symbol"])
            in_pool = code in selected_codes
            qs = (quotes.get(code) or []) if in_pool else []
            q = qs[0] if qs else {}
            prev = qs[1] if len(qs) > 1 else {}
            stock_rows.append(
                (
                    code,
                    r["name"],
                    None,
                    r["industry_code"] or "未分类",
                    "stock",
                    q.get("close") if in_pool else None,
                    (prev.get("close") or q.get("pre_close")) if in_pool else None,
                    q.get("open") if in_pool else None,
                    q.get("high") if in_pool else None,
                    q.get("low") if in_pool else None,
                    yi(r["float_mv"]) if in_pool else None,
                    r["pe_ttm"] if in_pool else None,
                    r["pb_mrq"] if in_pool else None,
                    r["dividend_yield_ttm"] if in_pool else None,
                    q.get("turnover") if in_pool else None,
                    q.get("volume") if in_pool else None,
                    q.get("amount") if in_pool else None,
                    None,
                    None,
                    f"{latest_date} 18:30:00",
                )
            )

        # ETF 最小快照（PG universe 不含 ETF）
        for code, name in ETF_CODES.items():
            if code in all_codes:
                continue
            bars = fetch_etf_bars(code)
            if not bars:
                continue
            last = bars[-1]
            prev = bars[-2] if len(bars) > 1 else last
            etf_bars[code] = bars
            stock_rows.append(
                (
                    code,
                    name,
                    code,
                    "宽基",
                    "etf",
                    last["close"],
                    prev["close"],
                    last["open"],
                    last["high"],
                    last["low"],
                    None,
                    None,
                    None,
                    None,
                    None,
                    last["volume"],
                    last["amount"],
                    None,
                    None,
                    f"{latest_date} 18:30:00",
                )
            )

        # 估值历史（仅选中池）
        val_rows = []
        for r in selected:
            code = bare(r["symbol"])
            rows = pg.execute(
                "SELECT trade_date, pe_ttm, pb_mrq FROM md_valuation_daily "
                "WHERE symbol=%s ORDER BY trade_date DESC LIMIT %s",
                (r["symbol"], args.bar_days),
            ).fetchall()
            for v in reversed(rows):
                val_rows.append((code, str(v["trade_date"]), v["pe_ttm"], v["pb_mrq"]))

        # 日线（仅选中池）
        bar_rows = []
        for r in selected:
            code = bare(r["symbol"])
            rows = pg.execute(
                """
                SELECT n.trade_date, n.open, n.high, n.low, n.close,
                       COALESCE(n.volume, h.volume) AS volume,
                       COALESCE(n.amount, h.amount) AS amount
                  FROM md_daily_bar n
                  LEFT JOIN md_daily_bar h
                    ON h.symbol=n.symbol AND h.trade_date=n.trade_date AND h.adjust='hfq'
                 WHERE n.symbol=%s AND n.adjust='none'
                 ORDER BY n.trade_date DESC LIMIT %s
                """,
                (r["symbol"], args.bar_days),
            ).fetchall()
            if not rows:
                rows = pg.execute(
                    "SELECT trade_date, open, high, low, close, volume, amount FROM md_daily_bar "
                    "WHERE symbol=%s AND adjust='hfq' ORDER BY trade_date DESC LIMIT %s",
                    (r["symbol"], args.bar_days),
                ).fetchall()
            for b in reversed(rows):
                bar_rows.append(
                    (
                        code,
                        str(b["trade_date"]),
                        b["open"],
                        b["high"],
                        b["low"],
                        b["close"],
                        b["volume"],
                        b["amount"],
                    )
                )

        for code, bars in etf_bars.items():
            for b in bars:
                bar_rows.append(
                    (
                        code,
                        b["date"],
                        b["open"],
                        b["high"],
                        b["low"],
                        b["close"],
                        b["volume"],
                        b["amount"],
                    )
                )

        # 财务（有数据的标的）
        fin_rows = []
        for r in selected:
            code = bare(r["symbol"])
            rows = pg.execute(
                """
                SELECT i.report_date, i.notice_date, i.revenue, i.net_profit, i.gross_profit,
                       cf.operating_cf, ind.roe, ind.gross_margin, ind.net_margin,
                       ind.revenue_yoy, ind.profit_yoy
                  FROM fin_income_statement i
                  LEFT JOIN LATERAL (
                    SELECT operating_cf FROM fin_cash_flow c
                     WHERE c.symbol=i.symbol AND c.report_date=i.report_date
                     ORDER BY c.notice_date DESC NULLS LAST LIMIT 1
                  ) cf ON TRUE
                  LEFT JOIN LATERAL (
                    SELECT roe, gross_margin, net_margin, revenue_yoy, profit_yoy
                      FROM fin_indicator x WHERE x.symbol=i.symbol AND x.report_date=i.report_date
                     ORDER BY x.notice_date DESC NULLS LAST LIMIT 1
                  ) ind ON TRUE
                 WHERE i.symbol=%s AND i.notice_date IS NOT NULL AND i.notice_date <= CURRENT_DATE
                 ORDER BY i.report_date ASC
                """,
                (r["symbol"],),
            ).fetchall()
            for f in rows:
                fin_rows.append(
                    (
                        code,
                        period_label(f["report_date"]),
                        yi(f["revenue"]),
                        pct100(f["revenue_yoy"]),
                        yi(f["net_profit"]),
                        pct100(f["profit_yoy"]),
                        pct100(f["gross_margin"]),
                        pct100(f["roe"]),
                        yi(f["operating_cf"]),
                        str(f["report_date"]),
                    )
                )

        # 指数
        index_rows = []
        for code, name in (("000300.SH", "沪深300"), ("000905.SH", "中证500")):
            rows = pg.execute(
                "SELECT trade_date, close FROM md_index_bar WHERE index_code=%s ORDER BY trade_date DESC LIMIT 2",
                (code,),
            ).fetchall()
            if rows:
                index_rows.append(
                    (
                        code.split(".")[0],
                        name,
                        rows[0]["close"],
                        rows[1]["close"] if len(rows) > 1 else rows[0]["close"],
                        f"{rows[0]['trade_date']} 18:30:00",
                    )
                )

        # 资讯/公告/研报（标题+链接）
        news_rows = []
        docs = pg.execute(
            "SELECT id, doc_type, symbol, title, summary, source, publish_at, url "
            "FROM doc_item ORDER BY publish_at DESC NULLS LAST LIMIT %s",
            (args.news_limit,),
        ).fetchall()
        for d in docs:
            kind = {"announcement": "公告", "research": "研报", "news": "要闻"}.get(d["doc_type"], "要闻")
            news_rows.append(
                (
                    f"doc-{d['id']}",
                    d["title"],
                    d["summary"] or "",
                    d["source"],
                    str(d["publish_at"] or "")[:19],
                    kind,
                    bare(d["symbol"]) if d["symbol"] else None,
                    None,
                    d["url"],
                )
            )

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM stocks")
        conn.executemany(
            "INSERT OR REPLACE INTO stocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            stock_rows,
        )
        conn.execute("DELETE FROM bars")
        conn.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?)", bar_rows)
        conn.execute("DELETE FROM valuations")
        conn.executemany("INSERT OR REPLACE INTO valuations VALUES (?,?,?,?)", val_rows)
        conn.execute("DELETE FROM financials")
        conn.executemany("INSERT OR REPLACE INTO financials VALUES (?,?,?,?,?,?,?,?,?,?)", fin_rows)
        conn.execute("DELETE FROM indices")
        conn.executemany("INSERT OR REPLACE INTO indices VALUES (?,?,?,?,?)", index_rows)
        conn.execute("DELETE FROM news")
        conn.executemany("INSERT OR REPLACE INTO news VALUES (?,?,?,?,?,?,?,?,?)", news_rows)
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('source','live')")
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('dataDate',?)", (str(latest_date),))
        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES ('updatedAt',?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),),
        )
        conn.commit()
    finally:
        conn.close()

    print(
        f"synced db={db_path} stocks={len(stock_rows)} bars={len(bar_rows)} "
        f"valuations={len(val_rows)} financials={len(fin_rows)} indices={len(index_rows)} news={len(news_rows)} "
        f"pool={len(selected)} dataDate={latest_date}"
    )


if __name__ == "__main__":
    main()
