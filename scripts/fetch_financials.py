#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从东方财富公开接口采集 A 股财务报表与公告，写入 PostgreSQL 服务层。

运行环境：base（需要 requests / psycopg），不要用 svquant 后端环境。
  /home/dev01/program/anaconda3/bin/python scripts/fetch_financials.py
  /home/dev01/program/anaconda3/bin/python scripts/fetch_financials.py --symbols 600519,000858 --pages 2

口径：
- 报表接口 RPT_DMSK_FN_INCOME / BALANCE / CASHFLOW，按 REPORT_DATE 倒序；累计口径。
- 防前视：所有行按 NOTICE_DATE <= today 过滤（接口可能返回明日才披露的报告）。
- 派生指标：roe/gross_margin/net_margin 为比例（0.15 = 15%），yoy 同为比例。
- 公告仅保留标题与链接，不落全文；幂等键 (source, content_hash)。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.core.db import get_conn  # noqa: E402
from services.core.env_config import env  # noqa: E402
from services.marketdata.schema import ensure_marketdata_schema  # noqa: E402

JOB = "fetch_financials"
SOURCE = "eastmoney"
SHANGHAI = ZoneInfo("Asia/Shanghai")

DEFAULT_SYMBOLS = (
    "600519",
    "000858",
    "300750",
    "600036",
    "000333",
    "601318",
    "000651",
    "002415",
)

FIN_BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
ANN_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
STATEMENTS = (
    ("income", "RPT_DMSK_FN_INCOME"),
    ("balance", "RPT_DMSK_FN_BALANCE"),
    ("cashflow", "RPT_DMSK_FN_CASHFLOW"),
)
FIN_PAGE_SIZE = 500
ANN_PAGE_SIZE = 50
STATEMENT_TYPE = "accumulated"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

_last_request = 0.0


# ----------------------------------------------------------------- 基础工具
def log(msg: str) -> None:
    print(f"[{datetime.now(SHANGHAI).strftime('%H:%M:%S')}] {msg}", flush=True)


def today_cn() -> date:
    return datetime.now(SHANGHAI).date()


def secucode(symbol: str) -> str:
    s = symbol.strip()
    if s.startswith(("6", "9")):
        return f"{s}.SH"
    if s.startswith(("0", "2", "3")):
        return f"{s}.SZ"
    if s.startswith(("4", "8")):
        return f"{s}.BJ"
    return f"{s}.SH"


def _throttle() -> None:
    """请求间礼貌间隔 0.3~0.5 秒。"""
    global _last_request
    wait = random.uniform(0.3, 0.5) - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(1, 4):
        _throttle()
        try:
            resp = SESSION.get(url, params=params, timeout=25)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - 网络/JSON 统一重试
            last_err = exc
            if attempt < 3:
                backoff = 2 ** (attempt - 1)
                log(f"  请求失败({attempt}/3)，{backoff}s 后重试: {type(exc).__name__}")
                time.sleep(backoff)
    raise RuntimeError(f"请求 3 次均失败: {url} -> {last_err}")


def parse_date(value: Any) -> date | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.split("T")[0].split(" ")[0]
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def num(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def sub(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def canonical_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def normalize_raw(row: dict[str, Any], symbol: str, code: str | None = None) -> dict[str, Any]:
    """原始行落库前统一 SECUCODE / SECURITY_CODE 口径。"""
    raw = dict(row)
    raw["SECUCODE"] = code or secucode(symbol)
    raw["SECURITY_CODE"] = symbol
    return raw


# ----------------------------------------------------------------- 抓取
def fetch_statement(report_name: str, symbol: str, pages: int, cutoff: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, pages + 1):
        payload = get_json(
            FIN_BASE,
            {
                "reportName": report_name,
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{symbol}")',
                "pageNumber": page,
                "pageSize": FIN_PAGE_SIZE,
                "sortColumns": "REPORT_DATE",
                "sortTypes": -1,
            },
        )
        if not payload.get("success"):
            log(f"  {report_name} 第 {page} 页返回 success=false: {payload.get('message')}")
            break
        result = payload.get("result") or {}
        batch = result.get("data") or []
        if not batch:
            break
        for row in batch:
            report_date = parse_date(row.get("REPORT_DATE"))
            notice_date = parse_date(row.get("NOTICE_DATE"))
            # 防前视：披露日晚于今天的行（含预告披露日）一律不落库
            if notice_date is not None and notice_date > cutoff:
                continue
            if report_date is None or report_date > cutoff:
                continue
            key = report_date.isoformat()
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
        if len(batch) < FIN_PAGE_SIZE:
            break
    return rows


def fetch_announcements(symbol: str, pages: int, cutoff: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, pages + 1):
        payload = get_json(
            ANN_URL,
            {
                "sr": -1,
                "page_size": ANN_PAGE_SIZE,
                "page_index": page,
                "ann_type": "A",
                "client_source": "web",
                "stock_list": symbol,
            },
        )
        if not payload.get("success"):
            log(f"  公告第 {page} 页返回 success=false: {payload.get('error')}")
            break
        data = payload.get("data") or {}
        batch = data.get("list") or []
        if not batch:
            break
        for row in batch:
            notice_date = parse_date(row.get("notice_date"))
            if notice_date is None or notice_date > cutoff:
                continue
            art_code = row.get("art_code")
            if not art_code or art_code in seen:
                continue
            seen.add(str(art_code))
            rows.append(row)
        if len(batch) < ANN_PAGE_SIZE:
            break
    return rows


# ----------------------------------------------------------------- 行构造
def build_income(symbol: str, rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        report_date = parse_date(row.get("REPORT_DATE"))
        revenue = num(row.get("TOTAL_OPERATE_INCOME"))
        cost = num(row.get("OPERATE_COST"))
        eps = num(row.get("BASIC_EPS"))
        if eps is None:
            eps = num(row.get("EPS_BASIC"))
        raw = normalize_raw(row, symbol)
        out.append(
            {
                "symbol": secucode(symbol),
                "report_date": report_date,
                "notice_date": parse_date(row.get("NOTICE_DATE")),
                "statement_type": STATEMENT_TYPE,
                "revenue": revenue,
                "operating_profit": num(row.get("OPERATE_PROFIT")),
                "net_profit": num(row.get("PARENT_NETPROFIT")),
                "gross_profit": sub(revenue, cost),
                "total_profit": num(row.get("TOTAL_PROFIT")),
                "eps": eps,
                "raw": Jsonb(raw),
                "source": SOURCE,
                "as_of": as_of,
                "raw_hash": canonical_hash(raw),
            }
        )
    return out


def build_balance(symbol: str, rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        raw = normalize_raw(row, symbol)
        out.append(
            {
                "symbol": secucode(symbol),
                "report_date": parse_date(row.get("REPORT_DATE")),
                "notice_date": parse_date(row.get("NOTICE_DATE")),
                "statement_type": STATEMENT_TYPE,
                "total_assets": num(row.get("TOTAL_ASSETS")),
                "total_liabilities": num(row.get("TOTAL_LIABILITIES")),
                "total_equity": num(row.get("TOTAL_EQUITY")),
                "current_assets": num(row.get("TOTAL_CURRENT_ASSETS")),
                "current_liabilities": num(row.get("TOTAL_CURRENT_LIAB")),
                "cash": num(row.get("MONETARYFUNDS")),
                "inventory": num(row.get("INVENTORY")),
                "receivables": num(row.get("ACCOUNTS_RECE")),
                "raw": Jsonb(raw),
                "source": SOURCE,
                "as_of": as_of,
                "raw_hash": canonical_hash(raw),
            }
        )
    return out


def build_cashflow(symbol: str, rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        operating_cf = num(row.get("NETCASH_OPERATE"))
        capex = num(row.get("CONSTRUCT_LONG_ASSET"))
        raw = normalize_raw(row, symbol)
        out.append(
            {
                "symbol": secucode(symbol),
                "report_date": parse_date(row.get("REPORT_DATE")),
                "notice_date": parse_date(row.get("NOTICE_DATE")),
                "statement_type": STATEMENT_TYPE,
                "operating_cf": operating_cf,
                "investing_cf": num(row.get("NETCASH_INVEST")),
                "financing_cf": num(row.get("NETCASH_FINANCE")),
                "free_cash_flow": sub(operating_cf, capex),
                "capex": capex,
                "raw": Jsonb(raw),
                "source": SOURCE,
                "as_of": as_of,
                "raw_hash": canonical_hash(raw),
            }
        )
    return out


def build_indicators(
    symbol: str,
    income: list[dict[str, Any]],
    balance: list[dict[str, Any]],
    as_of: date,
) -> list[dict[str, Any]]:
    income_by_date = {r["report_date"]: r for r in income}
    equity_by_date = {r["report_date"]: r.get("total_equity") for r in balance}
    out: list[dict[str, Any]] = []
    for report_date, inc in sorted(income_by_date.items()):
        try:
            prior_key = report_date.replace(year=report_date.year - 1)
        except ValueError:  # 2/29
            prior_key = None
        prior = income_by_date.get(prior_key) if prior_key else None
        revenue = inc.get("revenue")
        net_profit = inc.get("net_profit")
        gross_profit = inc.get("gross_profit")
        equity = equity_by_date.get(report_date)
        revenue_yoy = None
        profit_yoy = None
        if prior is not None:
            prev_rev = prior.get("revenue")
            prev_profit = prior.get("net_profit")
            if prev_rev not in (None, 0) and revenue is not None:
                revenue_yoy = revenue / prev_rev - 1.0
            if prev_profit not in (None, 0) and net_profit is not None:
                profit_yoy = net_profit / prev_profit - 1.0
        raw = {
            "basis": "computed",
            "net_profit": net_profit,
            "total_equity": equity,
            "revenue": revenue,
            "gross_profit": gross_profit,
            "prior_revenue": prior.get("revenue") if prior else None,
            "prior_net_profit": prior.get("net_profit") if prior else None,
            "eps_ttm": None,
        }
        out.append(
            {
                "symbol": secucode(symbol),
                "report_date": report_date,
                "notice_date": inc.get("notice_date"),
                "roe": div(net_profit, equity),
                "gross_margin": div(gross_profit, revenue),
                "net_margin": div(net_profit, revenue),
                "eps_ttm": None,  # 该接口无股本/TTM 口径，留空待估值源补齐
                "revenue_yoy": revenue_yoy,
                "profit_yoy": profit_yoy,
                "source": SOURCE,
                "as_of": as_of,
                "raw": Jsonb(raw),
            }
        )
    return out


def announcement_row(symbol: str, row: dict[str, Any], as_of: date) -> dict[str, Any] | None:
    notice_date = parse_date(row.get("notice_date"))
    art_code = row.get("art_code")
    title = (row.get("title") or row.get("title_ch") or "").strip()
    if notice_date is None or not art_code or not title:
        return None
    attach = row.get("attach_url") or row.get("attachUrl")
    url = attach or f"https://data.eastmoney.com/notices/detail/{symbol}/{art_code}.html"
    publish_at = datetime.combine(notice_date, dtime.min, tzinfo=SHANGHAI)
    content_hash = hashlib.sha256(
        f"{art_code}|{title}|{notice_date.isoformat()}".encode("utf-8")
    ).hexdigest()
    columns = row.get("columns") or []
    summary = None
    if isinstance(columns, list) and columns:
        names = [c.get("column_name") for c in columns if isinstance(c, dict) and c.get("column_name")]
        summary = "、".join(names) or None
    return {
        "doc_type": "announcement",
        "symbol": secucode(symbol),
        "title": title,
        "publish_at": publish_at,
        "url": url,
        "source": SOURCE,
        "content_hash": content_hash,
        "summary": summary,
        "raw": Jsonb(dict(row)),
        "as_of": as_of,
    }


# ----------------------------------------------------------------- 写库
INCOME_SQL = """
INSERT INTO fin_income_statement
  (symbol, report_date, notice_date, statement_type, revenue, operating_profit,
   net_profit, gross_profit, total_profit, eps, raw, source, as_of, raw_hash)
VALUES
  (%(symbol)s, %(report_date)s, %(notice_date)s, %(statement_type)s, %(revenue)s,
   %(operating_profit)s, %(net_profit)s, %(gross_profit)s, %(total_profit)s, %(eps)s,
   %(raw)s, %(source)s, %(as_of)s, %(raw_hash)s)
ON CONFLICT (symbol, report_date, statement_type, source) DO UPDATE SET
  notice_date     = EXCLUDED.notice_date,
  revenue         = EXCLUDED.revenue,
  operating_profit= EXCLUDED.operating_profit,
  net_profit      = EXCLUDED.net_profit,
  gross_profit    = EXCLUDED.gross_profit,
  total_profit    = EXCLUDED.total_profit,
  eps             = EXCLUDED.eps,
  raw             = EXCLUDED.raw,
  as_of           = EXCLUDED.as_of,
  raw_hash        = EXCLUDED.raw_hash
"""

BALANCE_SQL = """
INSERT INTO fin_balance_sheet
  (symbol, report_date, notice_date, statement_type, total_assets, total_liabilities,
   total_equity, current_assets, current_liabilities, cash, inventory, receivables,
   raw, source, as_of, raw_hash)
VALUES
  (%(symbol)s, %(report_date)s, %(notice_date)s, %(statement_type)s, %(total_assets)s,
   %(total_liabilities)s, %(total_equity)s, %(current_assets)s, %(current_liabilities)s,
   %(cash)s, %(inventory)s, %(receivables)s, %(raw)s, %(source)s, %(as_of)s, %(raw_hash)s)
ON CONFLICT (symbol, report_date, statement_type, source) DO UPDATE SET
  notice_date       = EXCLUDED.notice_date,
  total_assets      = EXCLUDED.total_assets,
  total_liabilities = EXCLUDED.total_liabilities,
  total_equity      = EXCLUDED.total_equity,
  current_assets    = EXCLUDED.current_assets,
  current_liabilities = EXCLUDED.current_liabilities,
  cash              = EXCLUDED.cash,
  inventory         = EXCLUDED.inventory,
  receivables       = EXCLUDED.receivables,
  raw               = EXCLUDED.raw,
  as_of             = EXCLUDED.as_of,
  raw_hash          = EXCLUDED.raw_hash
"""

CASHFLOW_SQL = """
INSERT INTO fin_cash_flow
  (symbol, report_date, notice_date, statement_type, operating_cf, investing_cf,
   financing_cf, free_cash_flow, capex, raw, source, as_of, raw_hash)
VALUES
  (%(symbol)s, %(report_date)s, %(notice_date)s, %(statement_type)s, %(operating_cf)s,
   %(investing_cf)s, %(financing_cf)s, %(free_cash_flow)s, %(capex)s, %(raw)s,
   %(source)s, %(as_of)s, %(raw_hash)s)
ON CONFLICT (symbol, report_date, statement_type, source) DO UPDATE SET
  notice_date     = EXCLUDED.notice_date,
  operating_cf    = EXCLUDED.operating_cf,
  investing_cf    = EXCLUDED.investing_cf,
  financing_cf    = EXCLUDED.financing_cf,
  free_cash_flow  = EXCLUDED.free_cash_flow,
  capex           = EXCLUDED.capex,
  raw             = EXCLUDED.raw,
  as_of           = EXCLUDED.as_of,
  raw_hash        = EXCLUDED.raw_hash
"""

INDICATOR_SQL = """
INSERT INTO fin_indicator
  (symbol, report_date, notice_date, roe, gross_margin, net_margin, eps_ttm,
   revenue_yoy, profit_yoy, source, as_of, raw)
VALUES
  (%(symbol)s, %(report_date)s, %(notice_date)s, %(roe)s, %(gross_margin)s, %(net_margin)s,
   %(eps_ttm)s, %(revenue_yoy)s, %(profit_yoy)s, %(source)s, %(as_of)s, %(raw)s)
ON CONFLICT (symbol, report_date, source) DO UPDATE SET
  notice_date  = EXCLUDED.notice_date,
  roe          = EXCLUDED.roe,
  gross_margin = EXCLUDED.gross_margin,
  net_margin   = EXCLUDED.net_margin,
  eps_ttm      = EXCLUDED.eps_ttm,
  revenue_yoy  = EXCLUDED.revenue_yoy,
  profit_yoy   = EXCLUDED.profit_yoy,
  as_of        = EXCLUDED.as_of,
  raw          = EXCLUDED.raw
"""

DOC_SQL = """
INSERT INTO doc_item
  (doc_type, symbol, title, publish_at, url, source, content_hash, summary, raw, as_of)
VALUES
  (%(doc_type)s, %(symbol)s, %(title)s, %(publish_at)s, %(url)s, %(source)s,
   %(content_hash)s, %(summary)s, %(raw)s, %(as_of)s)
ON CONFLICT (source, content_hash) DO NOTHING
"""


def upsert_rows(conn, sql: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def insert_docs(conn, rows: list[dict[str, Any]]) -> int:
    inserted = 0
    for row in rows:
        cur = conn.execute(DOC_SQL, row)
        if cur.rowcount:
            inserted += cur.rowcount
    return inserted


def start_run() -> int:
    with get_conn(autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO ingest_run (job, source, status) VALUES (%s, %s, 'running') RETURNING run_id",
            (JOB, SOURCE),
        ).fetchone()
        return int(row["run_id"])


def finish_run(run_id: int, *, status: str, rows: int | None, error: str | None, detail: Any) -> None:
    with get_conn(autocommit=True) as conn:
        conn.execute(
            """
            UPDATE ingest_run
               SET finished_at = NOW(), status = %s, rows = %s, error = %s, detail = %s
             WHERE run_id = %s
            """,
            (status, rows, error, Jsonb(detail) if detail is not None else None, run_id),
        )


def update_watermark(last_data_date: date | None) -> date | None:
    with get_conn(autocommit=True) as conn:
        row = conn.execute(
            """
            INSERT INTO ingest_watermark (job, source, last_success_at, last_data_date)
            VALUES (%s, %s, NOW(), %s)
            ON CONFLICT (job, source) DO UPDATE SET
              last_success_at = EXCLUDED.last_success_at,
              last_data_date  = GREATEST(ingest_watermark.last_data_date, EXCLUDED.last_data_date)
            RETURNING last_data_date
            """,
            (JOB, SOURCE, last_data_date),
        ).fetchone()
        return row["last_data_date"] if row else last_data_date


# ----------------------------------------------------------------- 主流程
def parse_symbols(text: str) -> list[str]:
    out: list[str] = []
    for part in text.replace("，", ",").split(","):
        s = part.strip()
        if s and s not in out:
            out.append(s)
    return out


def run(args: argparse.Namespace) -> int:
    symbols = parse_symbols(args.symbols)
    if not symbols:
        raise SystemExit("--symbols 为空")
    cutoff = today_cn()

    ensure_marketdata_schema()
    run_id = start_run()
    log(f"ingest_run #{run_id} 开始：symbols={len(symbols)} pages={args.pages} cutoff={cutoff}")

    per_symbol: dict[str, dict[str, int]] = {}
    all_dates: list[date] = []
    total_rows = 0
    error: str | None = None
    try:
        for symbol in symbols:
            counts = {"income": 0, "balance": 0, "cashflow": 0, "indicator": 0, "announcement": 0}
            log(f"{symbol} 抓取中…")

            inc_raw = fetch_statement("RPT_DMSK_FN_INCOME", symbol, args.pages, cutoff)
            bal_raw = fetch_statement("RPT_DMSK_FN_BALANCE", symbol, args.pages, cutoff)
            cf_raw = fetch_statement("RPT_DMSK_FN_CASHFLOW", symbol, args.pages, cutoff)

            income = build_income(symbol, inc_raw, cutoff)
            balance = build_balance(symbol, bal_raw, cutoff)
            cash = build_cashflow(symbol, cf_raw, cutoff)
            indicators = build_indicators(symbol, income, balance, cutoff)

            docs: list[dict[str, Any]] = []
            if not args.skip_announcements:
                ann_raw = fetch_announcements(symbol, args.pages, cutoff)
                docs = [d for d in (announcement_row(symbol, r, cutoff) for r in ann_raw) if d]

            with get_conn() as conn:
                counts["income"] = upsert_rows(conn, INCOME_SQL, income)
                counts["balance"] = upsert_rows(conn, BALANCE_SQL, balance)
                counts["cashflow"] = upsert_rows(conn, CASHFLOW_SQL, cash)
                counts["indicator"] = upsert_rows(conn, INDICATOR_SQL, indicators)
                if docs:
                    counts["announcement"] = insert_docs(conn, docs)

            all_dates.extend(r["report_date"] for r in income if r["report_date"])
            sym_total = sum(counts.values())
            total_rows += sym_total
            per_symbol[symbol] = counts
            log(
                f"{symbol} 完成：income={counts['income']} balance={counts['balance']} "
                f"cashflow={counts['cashflow']} indicator={counts['indicator']} "
                f"announcement={counts['announcement']}"
            )
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"[:2000]
        finish_run(
            run_id,
            status="failed",
            rows=total_rows,
            error=error,
            detail={"symbols": symbols, "pages": args.pages, "cutoff": str(cutoff), "per_symbol": per_symbol},
        )
        raise

    last_data_date = max(all_dates) if all_dates else None
    detail = {
        "symbols": symbols,
        "pages": args.pages,
        "skip_announcements": args.skip_announcements,
        "cutoff": str(cutoff),
        "per_symbol": per_symbol,
    }
    finish_run(run_id, status="success", rows=total_rows, error=None, detail=detail)
    watermark = update_watermark(last_data_date)

    log("---- 汇总 ----")
    for symbol in symbols:
        c = per_symbol.get(symbol, {})
        log(
            f"  {symbol}: income={c.get('income', 0)} balance={c.get('balance', 0)} "
            f"cashflow={c.get('cashflow', 0)} indicator={c.get('indicator', 0)} "
            f"announcement={c.get('announcement', 0)}"
        )
    log(f"合计 {total_rows} 行，run_id={run_id}，watermark={watermark}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="采集东方财富 A 股财报与公告到 PostgreSQL")
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="逗号分隔的 A 股代码，默认 8 只观察池",
    )
    parser.add_argument("--pages", type=int, default=10, help="每个接口最多翻页数（默认 10）")
    parser.add_argument("--skip-announcements", action="store_true", help="跳过公告采集")
    args = parser.parse_args()
    if args.pages < 1:
        raise SystemExit("--pages 必须 >= 1")
    # 确保 DATABASE_URL 可从 backend/.env 读取（env_config 在首次调用时加载）
    if not env("DATABASE_URL"):
        raise SystemExit("backend/.env 缺少 DATABASE_URL")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
