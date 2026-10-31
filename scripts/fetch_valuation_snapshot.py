#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""补全个股最新总股本/总市值（东方财富估值快照）。

parquet 的 `date_sequence.ths_current_mv_stock` 是流通市值，没有总股本；
本脚本只对研究池逐只取最新估值快照，写 `md_valuation_daily.total_shares/total_mv`
与 `fin_share_capital`。不做全市场批量（避免 5,956 次请求）。

  /home/dev01/program/anaconda3/bin/python scripts/fetch_valuation_snapshot.py
  /home/dev01/program/anaconda3/bin/python scripts/fetch_valuation_snapshot.py --symbols 600519,000858
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.core.db import get_conn  # noqa: E402
from services.core.env_config import env  # noqa: E402
from services.marketdata.schema import ensure_marketdata_schema  # noqa: E402

BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
}
DEFAULT = ("600519", "000858", "300750", "600036", "000333", "601318", "000651", "002415")


def secucode(symbol: str) -> str:
    return f"{symbol}.SH" if symbol.startswith(("6", "9")) else f"{symbol}.SZ"


def fetch(symbol: str) -> dict[str, Any] | None:
    params = {
        "reportName": "RPT_VALUEANALYSIS_DET",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{symbol}")',
        "pageNumber": 1,
        "pageSize": 1,
        "sortColumns": "TRADE_DATE",
        "sortTypes": -1,
    }
    for attempt in range(3):
        try:
            r = requests.get(BASE, params=params, headers=HEADERS, timeout=25)
            r.raise_for_status()
            data = r.json()
            rows = ((data.get("result") or {}).get("data") or [])
            return rows[0] if rows else None
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT))
    args = ap.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    ensure_marketdata_schema(include_indexes=False)
    ok = 0
    with get_conn() as conn:
        for s in symbols:
            row = fetch(s)
            if not row:
                print(f"[{s}] 无估值快照")
                continue
            trade_date = str(row.get("TRADE_DATE") or "")[:10]
            total_shares = row.get("TOTAL_SHARES")
            total_mv = row.get("TOTAL_MARKET_CAP")
            if trade_date and total_shares:
                conn.execute(
                    "UPDATE md_valuation_daily SET total_shares=%s, total_mv=%s "
                    "WHERE symbol=%s AND trade_date=%s",
                    (total_shares, total_mv, secucode(s), trade_date),
                )
                conn.execute(
                    """
                    INSERT INTO fin_share_capital
                      (symbol, effective_date, announce_date, total_shares, float_shares, source, as_of, raw)
                    VALUES (%s,%s,%s,%s,%s,'eastmoney',%s,%s)
                    ON CONFLICT (symbol, effective_date, source) DO UPDATE
                      SET total_shares=EXCLUDED.total_shares,
                          float_shares=EXCLUDED.float_shares,
                          raw=EXCLUDED.raw,
                          as_of=EXCLUDED.as_of
                    """,
                    (
                        secucode(s),
                        trade_date,
                        None,
                        total_shares,
                        row.get("FREE_SHARES_A"),
                        date.today(),
                        Jsonb(row),
                    ),
                )
                ok += 1
                print(f"[{s}] {trade_date} total_shares={total_shares} total_mv={total_mv}")
            else:
                print(f"[{s}] 快照缺少 TOTAL_SHARES")
    print(f"done {ok}/{len(symbols)}")


if __name__ == "__main__":
    main()
