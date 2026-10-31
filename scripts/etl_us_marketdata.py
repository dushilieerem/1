#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把美股 parquet 同步到 PostgreSQL 服务层（与 A 股同一套 md_* 表）。

背景：主观投研端按语言切换研究范围（中文 A 股 / 英文美股），美股需要
`ref_security`、`ref_trading_calendar` 与 `md_daily_bar`。美股没有财务/估值/
行业数据，研究页会显示“待补充”。

  /home/dev01/program/anaconda3/bin/python scripts/etl_us_marketdata.py
  /home/dev01/program/anaconda3/bin/python scripts/etl_us_marketdata.py --days 750
"""
from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.core.env_config import env  # noqa: E402
from services.marketdata.schema import ensure_marketdata_schema  # noqa: E402

MARKETDATA = Path("/home/dev01/project/marketdata/us_stock")
UNIVERSE = MARKETDATA / "universe.parquet"
CALENDAR = MARKETDATA / "calendar.parquet"
HFQ = MARKETDATA / "quotes_hfq.parquet"
BFQ = MARKETDATA / "quotes_bfq.parquet"
FIELDS_HFQ = ("open", "high", "low", "close", "volume", "amount", "turnover")
FIELDS_BFQ = ("open", "high", "low", "close")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def db_url() -> str:
    url = env("DATABASE_URL", "") or ""
    if not url:
        raise SystemExit("backend/.env 缺少 DATABASE_URL")
    return url


def _read(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if columns is None:
        table = pq.read_table(path, use_pandas_metadata=False)
    else:
        table = pq.read_table(path, columns=columns, use_pandas_metadata=False)
    return table.to_pandas(ignore_metadata=True)


def _col(symbol: str, field: str) -> str:
    return f"('{symbol}', '{field}')"


def _f(v) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    return repr(float(v)) if isinstance(v, float) else str(v)


def _batch(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _copy(conn, table: str, columns: tuple[str, ...], rows: list[tuple]) -> int:
    if not rows:
        return 0
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    buf.seek(0)
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
            cp.write(buf.getvalue())
    return len(rows)


def ensure_ref(conn) -> list[str]:
    uni = _read(UNIVERSE, ["thscode", "name"]).fillna("")
    symbols = [str(s) for s in uni["thscode"].tolist() if s]
    rows = []
    for sym, name in zip(uni["thscode"], uni["name"]):
        sym = str(sym)
        if not sym:
            continue
        exchange = sym.split(".")[-1] if "." in sym else None
        rows.append((sym, str(name) or None, "US", exchange, None, None, None, "listed", "ifind"))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ref_security WHERE market='US'")
        _copy(
            conn,
            "ref_security",
            ("symbol", "name", "market", "exchange", "board", "list_date", "delist_date", "status", "source"),
            rows,
        )
        cal = _read(CALENDAR, ["date", "is_trade_day"]).dropna(subset=["date"])
        cal_rows = [("US", str(d)[:10], str(bool(v)).lower(), "ifind") for d, v in zip(cal["date"], cal["is_trade_day"])]
        cal_rows = list({r[1]: r for r in cal_rows}.values())
        cur.execute("DELETE FROM ref_trading_calendar WHERE market='US'")
        _copy(
            conn,
            "ref_trading_calendar",
            ("market", "trade_date", "is_open", "source"),
            cal_rows,
        )
    conn.commit()
    log(f"ref_security US={len(rows)} calendar US={len(cal_rows)}")
    return symbols


def _available_symbols(path: Path, field: str) -> set[str]:
    """从宽表列名解析出实际存在的 symbol；universe 与 quotes 列集合并不完全一致。"""
    names = pq.ParquetFile(path).schema_arrow.names
    out: set[str] = set()
    for name in names:
        if not name.startswith("('"):
            continue
        try:
            pair = ast.literal_eval(name)
        except (ValueError, SyntaxError):
            continue
        if isinstance(pair, tuple) and len(pair) == 2 and pair[1] == field:
            out.add(str(pair[0]))
    return out


def load_bars(conn, symbols: list[str], days: int, batch_symbols: int) -> tuple[int, int]:
    cutoff = (date.today() - timedelta(days=max(30, days))).isoformat()
    hfq_syms = _available_symbols(HFQ, "close")
    bfq_syms = _available_symbols(BFQ, "close")
    log(f"quote columns hfq={len(hfq_syms)} bfq={len(bfq_syms)} universe={len(symbols)}")
    # 一次性读入宽表，避免 pyarrow 把 symbol 里的 "." 当嵌套字段路径。
    hfq_df = _read(HFQ)
    hfq_df = hfq_df[hfq_df["date"] >= cutoff]
    bfq_df = _read(BFQ)
    bfq_df = bfq_df[bfq_df["date"] >= cutoff]
    log(f"loaded wide tables hfq={len(hfq_df)} rows bfq={len(bfq_df)} rows")
    total_h = total_b = 0
    for bi, batch_all in enumerate(_batch(symbols, batch_symbols), 1):
        batch = [s for s in batch_all if s in hfq_syms or s in bfq_syms]
        if not batch:
            continue
        # hfq（按实际读入的 DataFrame 列再过滤一次，schema 与 pandas 列可能不完全一致）
        batch_h = [
            s for s in batch
            if s in hfq_syms and all(_col(s, f) in hfq_df.columns for f in FIELDS_HFQ)
        ]
        cols = ["date"] + [_col(s, f) for s in batch_h for f in FIELDS_HFQ]
        df = hfq_df[cols] if batch_h and all(c in hfq_df.columns for c in cols) else pd.DataFrame()
        rows = []
        for s in batch_h:
            sub = df[["date"] + [_col(s, f) for f in FIELDS_HFQ]].copy()
            sub.columns = ["date"] + list(FIELDS_HFQ)
            sub = sub.dropna(subset=["date"]).sort_values("date")
            prev = None
            for r in sub.itertuples(index=False):
                close = None if pd.isna(r.close) else float(r.close)
                rows.append(
                    (
                        s, str(r.date)[:10], _f(r.open), _f(r.high), _f(r.low), _f(close), _f(prev),
                        _f(r.volume), _f(r.amount), _f(r.turnover), "hfq", "ifind",
                    )
                )
                prev = close
        with conn.cursor() as cur:
            cur.execute("DELETE FROM md_daily_bar WHERE adjust='hfq' AND symbol = ANY(%s)", (batch_h,))
        total_h += _copy(
            conn,
            "md_daily_bar",
            ("symbol", "trade_date", "open", "high", "low", "close", "pre_close", "volume", "amount", "turnover", "adjust", "source"),
            rows,
        )
        # bfq -> adjust='none'
        batch_b = [
            s for s in batch
            if s in bfq_syms and all(_col(s, f) in bfq_df.columns for f in FIELDS_BFQ)
        ]
        cols = ["date"] + [_col(s, f) for s in batch_b for f in FIELDS_BFQ]
        df = bfq_df[cols] if batch_b and all(c in bfq_df.columns for c in cols) else pd.DataFrame()
        rows = []
        for s in batch_b:
            sub = df[["date"] + [_col(s, f) for f in FIELDS_BFQ]].copy()
            sub.columns = ["date"] + list(FIELDS_BFQ)
            sub = sub.dropna(subset=["date"]).sort_values("date")
            prev = None
            for r in sub.itertuples(index=False):
                close = None if pd.isna(r.close) else float(r.close)
                rows.append(
                    (s, str(r.date)[:10], _f(r.open), _f(r.high), _f(r.low), _f(close), _f(prev), None, None, None, "none", "ifind")
                )
                prev = close
        with conn.cursor() as cur:
            cur.execute("DELETE FROM md_daily_bar WHERE adjust='none' AND symbol = ANY(%s)", (batch_b,))
        total_b += _copy(
            conn,
            "md_daily_bar",
            ("symbol", "trade_date", "open", "high", "low", "close", "pre_close", "volume", "amount", "turnover", "adjust", "source"),
            rows,
        )
        conn.commit()
        log(f"US bars batch {bi} hfq_total={total_h} none_total={total_b}")
    return total_h, total_b


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=750, help="只加载最近 N 个自然日，默认 750")
    ap.add_argument("--batch-symbols", type=int, default=200)
    ap.add_argument("--limit-symbols", type=int, default=0, help="仅调试：只处理前 N 只")
    ap.add_argument("--skip-bars", action="store_true")
    args = ap.parse_args()
    ensure_marketdata_schema(include_indexes=False)
    with psycopg.connect(db_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO ingest_run (job, source, status) VALUES ('etl_us_marketdata','ifind','running') RETURNING run_id")
            run_id = cur.fetchone()[0]
        conn.commit()
        started = time.time()
        try:
            symbols = ensure_ref(conn)
            if args.limit_symbols:
                symbols = symbols[: args.limit_symbols]
            h = b = 0
            if not args.skip_bars:
                h, b = load_bars(conn, symbols, args.days, args.batch_symbols)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE ingest_run SET status='success', finished_at=NOW(), detail=%s WHERE run_id=%s",
                    (json.dumps({"symbols": len(symbols), "hfq": h, "none": b, "seconds": round(time.time() - started, 1)}), run_id),
                )
                cur.execute(
                    "INSERT INTO ingest_watermark (job,source,last_success_at,last_data_date) VALUES ('etl_us_marketdata','ifind',NOW(),%s) "
                    "ON CONFLICT (job,source) DO UPDATE SET last_success_at=NOW(), last_data_date=EXCLUDED.last_data_date",
                    (date.today(),),
                )
            conn.commit()
            log(f"done symbols={len(symbols)} hfq={h} none={b} seconds={time.time()-started:.1f}")
        except Exception as exc:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("UPDATE ingest_run SET status='failed', finished_at=NOW(), error=%s WHERE run_id=%s", (str(exc)[:2000], run_id))
            conn.commit()
            raise


if __name__ == "__main__":
    main()
