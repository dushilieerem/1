#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 fin_* 明细表桥接到 financial_statements（PIT API 使用）。

fetch_financials.py 写入的是 fin_income_statement / fin_balance_sheet /
fin_cash_flow / fin_indicator；SVQuant 的 /api/market-data/financials/*
读取的是 financial_statements（data JSONB）。

  DATABASE_URL=... /home/dev01/program/anaconda3/bin/python scripts/sync_financial_statements.py
  ... --symbols 600519,000858

规则：
- announce_date = notice_date；缺失公告日的行跳过，避免用报告期回填造成前视。
- 只同步当前 fin_* 中已存在的报告期（不补造）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.data.financial_store import ensure_financial_schema  # noqa: E402


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("需要 DATABASE_URL")
    return url


def _data(row: dict) -> dict:
    return {k: v for k, v in row.items() if v is not None}


def run(symbols: list[str] | None) -> tuple[int, int]:
    ensure_financial_schema()
    where = ""
    params: tuple = ()
    if symbols:
        where = " WHERE symbol = ANY(%s)"
        params = (symbols,)
    total = skipped = 0
    with psycopg.connect(_db_url(), row_factory=psycopg.rows.dict_row) as conn:
        for stype, table, fields in (
            (
                "income",
                "fin_income_statement",
                ("revenue", "operating_profit", "net_profit", "gross_profit", "total_profit", "eps"),
            ),
            (
                "balance",
                "fin_balance_sheet",
                ("total_assets", "total_liabilities", "total_equity", "current_assets", "current_liabilities", "cash", "inventory", "receivables"),
            ),
            (
                "cashflow",
                "fin_cash_flow",
                ("operating_cf", "investing_cf", "financing_cf", "free_cash_flow", "capex"),
            ),
            (
                "indicator",
                "fin_indicator",
                ("roe", "gross_margin", "net_margin", "eps_ttm", "revenue_yoy", "profit_yoy"),
            ),
        ):
            rows = conn.execute(
                f"SELECT symbol, report_date, notice_date, source, {', '.join(fields)} FROM {table}{where}",
                params,
            ).fetchall()
            renamed = {
                "operating_cf": "operating_cash_flow",
                "investing_cf": "investing_cash_flow",
                "financing_cf": "financing_cash_flow",
            }
            for row in rows:
                announce = row.get("notice_date")
                if announce is None:
                    skipped += 1
                    continue
                data = {}
                for f in fields:
                    if row.get(f) is not None:
                        data[renamed.get(f, f)] = row[f]
                conn.execute(
                    """
                    INSERT INTO financial_statements
                      (symbol, report_period, announce_date, statement_type, data, source)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (symbol, report_period, statement_type) DO UPDATE SET
                      announce_date = EXCLUDED.announce_date,
                      data = EXCLUDED.data,
                      source = EXCLUDED.source,
                      updated_at = NOW()
                    """,
                    (
                        row["symbol"],
                        row["report_date"],
                        announce,
                        stype,
                        json.dumps(data, ensure_ascii=False, default=str),
                        row.get("source") or "eastmoney",
                    ),
                )
                total += 1
        conn.commit()
    return total, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="", help="逗号分隔证券代码；空=全部已抓取")
    args = ap.parse_args()
    symbols = [s.strip() for s in args.symbols.replace("，", ",").split(",") if s.strip()]
    total, skipped = run(symbols or None)
    print(f"[sync_financial_statements] 写入 {total} 条，跳过无公告日 {skipped} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
