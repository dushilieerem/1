#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""非破坏式补载 marketdata 服务层（不清空、不覆盖已有行）。

用于生产只补缺失数据：md_daily_bar / md_valuation_daily / md_status_daily。
与 etl_marketdata.py 的区别：不做 TRUNCATE / DELETE，全部 INSERT ... ON CONFLICT DO NOTHING。

  DATABASE_URL=... MARKETDATA_DIR=/path/marketdata \
    /home/dev01/program/anaconda3/bin/python scripts/load_marketdata_missing.py --from 2016-01-01
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.marketdata.schema import ensure_marketdata_schema  # noqa: E402

DATA = Path(os.environ.get("MARKETDATA_DIR", "/home/dev01/project/marketdata"))
HFQ = DATA / "market_data/market_data_hfq.parquet"
UNADJ = DATA / "unadjusted_price/unadjusted_price.parquet"
VALUATION = DATA / "date_sequence/date_sequence.parquet"
UNIVERSE = DATA / "universe/a_share.parquet"


def log(msg: str) -> None:
    print(msg, flush=True)


def _read(path: Path, columns: list[str]) -> pd.DataFrame:
    return pq.read_table(path, columns=columns).to_pandas(ignore_metadata=True)


def _col(symbol: str, field: str) -> str:
    return f"('{symbol}', '{field}')"


def _f(v):
    try:
        return None if v is None or pd.isna(v) else float(v)
    except Exception:
        return None


def _batch(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _copy_upsert(conn, table: str, columns: tuple[str, ...], rows: list[tuple]) -> int:
    if not rows:
        return 0
    tmp = f"tmp_{table}_{os.getpid()}"
    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE {tmp} (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP")
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        buf.seek(0)
        with cur.copy(
            f"COPY {tmp} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv, NULL '')"
        ) as copy:
            copy.write(buf.getvalue())
        cur.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"SELECT {', '.join(columns)} FROM {tmp} ON CONFLICT DO NOTHING"
        )
    conn.commit()
    return len(rows)


def load_bars(conn, from_date: date, batch_symbols: int) -> int:
    symbols = [
        str(x)
        for x in _read(UNIVERSE, ["thscode"])["thscode"].tolist()
        if isinstance(x, str) and x
    ]
    total = 0
    for bi, batch in enumerate(_batch(symbols, batch_symbols), 1):
        for path, fields, adjust in (
            (HFQ, ("open", "high", "low", "close", "volume", "amount", "turnover"), "hfq"),
            (UNADJ, ("open", "high", "low", "close"), "none"),
        ):
            cols = ["date"]
            for s in batch:
                cols += [_col(s, f) for f in fields]
            df = _read(path, cols)
            df = df[df["date"] >= from_date.isoformat()]
            rows = []
            for s in batch:
                sub = df[["date"] + [_col(s, f) for f in fields]].copy()
                sub.columns = ["date", *fields]
                sub = sub.dropna(subset=["date"]).sort_values("date")
                for r in sub.itertuples(index=False):
                    rows.append(
                        (
                            s,
                            str(r.date)[:10],
                            _f(r.open),
                            _f(r.high),
                            _f(r.low),
                            _f(r.close),
                            _f(getattr(r, "volume", None)),
                            _f(getattr(r, "amount", None)),
                            _f(getattr(r, "turnover", None)),
                            adjust,
                            "ifind",
                        )
                    )
            total += _copy_upsert(
                conn,
                "md_daily_bar",
                ("symbol", "trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "adjust", "source"),
                rows,
            )
        log(f"bars batch {bi} rows_total={total}")
    return total


def load_valuation(conn, from_date: date, batch_symbols: int) -> int:
    symbols = [
        str(x)
        for x in _read(UNIVERSE, ["thscode"])["thscode"].tolist()
        if isinstance(x, str) and x
    ]
    fields = {
        "pe_ttm": "ths_pe_ttm_stock",
        "pb_mrq": "ths_pb_mrq_stock",
        "pcf_ocf_ttm": "ths_pcf_operating_cash_flow_ttm_stock",
        "dividend_yield_ttm": "ths_dividend_yield_ttm_stock",
        "float_mv": "ths_current_mv_stock",
    }
    total = 0
    for bi, batch in enumerate(_batch(symbols, batch_symbols), 1):
        cols = ["date"]
        for s in batch:
            cols += [_col(s, f) for f in fields.values()]
        df = _read(VALUATION, cols)
        df = df[df["date"] >= from_date.isoformat()]
        rows = []
        for s in batch:
            sub = df[["date"] + [_col(s, f) for f in fields.values()]].copy()
            sub.columns = ["date", *fields.keys()]
            sub = sub.dropna(subset=["date"]).sort_values("date")
            for r in sub.itertuples(index=False):
                rows.append(
                    (
                        s,
                        str(r.date)[:10],
                        _f(r.pe_ttm),
                        _f(r.pb_mrq),
                        _f(r.pcf_ocf_ttm),
                        _f(r.dividend_yield_ttm),
                        _f(r.float_mv),
                        None,
                        None,
                        "ifind",
                    )
                )
        total += _copy_upsert(
            conn,
            "md_valuation_daily",
            ("symbol", "trade_date", "pe_ttm", "pb_mrq", "pcf_ocf_ttm", "dividend_yield_ttm", "float_mv", "total_mv", "total_shares", "source"),
            rows,
        )
        log(f"valuation batch {bi} rows_total={total}")
    return total


def main() -> int:
    if os.environ.get("ALLOW_LEGACY_COLLECT") != "1":
        raise SystemExit(
            "该采集脚本已迁移到独立数据平台 /home/dev01/project/svquant-data；"
            "如确需应急运行，设置 ALLOW_LEGACY_COLLECT=1。"
        )
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default="2016-01-01")
    ap.add_argument("--batch-symbols", type=int, default=200)
    ap.add_argument("--skip-bars", action="store_true")
    ap.add_argument("--skip-valuation", action="store_true")
    args = ap.parse_args()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("需要 DATABASE_URL")
    ensure_marketdata_schema(include_indexes=False)
    from_date = date.fromisoformat(args.from_date)
    with psycopg.connect(url) as conn:
        if not args.skip_bars:
            n = load_bars(conn, from_date, args.batch_symbols)
            log(f"md_daily_bar inserted={n}")
        if not args.skip_valuation:
            n = load_valuation(conn, from_date, args.batch_symbols)
            log(f"md_valuation_daily inserted={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
