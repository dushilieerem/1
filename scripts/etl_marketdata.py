#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 marketdata parquet 同步到 PostgreSQL 服务层。

运行环境：base（需要 pyarrow / pandas / psycopg），不要用 svquant 后端环境。
  /home/dev01/program/anaconda3/bin/python scripts/etl_marketdata.py --truncate

默认只同步 2016-01-01 起的服务层窗口；更早历史查询回退 parquet。
这是**全量重载**（按 symbol 分批 DELETE+COPY），不是增量任务；数据 release 更新后跑一次即可。
每日增量请用 `invest-api/scripts/fetch_live.py`，或后续单独实现按日期 upsert。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import psycopg

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from services.core.env_config import env  # noqa: E402
from services.marketdata.schema import (  # noqa: E402
    ensure_marketdata_indexes,
    ensure_marketdata_schema,
)

MARKETDATA = Path(os.environ.get("MARKETDATA_DIR", "/home/dev01/project/marketdata"))
HFQ = MARKETDATA / "market_data/market_data_hfq.parquet"
UNADJ = MARKETDATA / "unadjusted_price/unadjusted_price.parquet"
VALUATION = MARKETDATA / "date_sequence/date_sequence.parquet"
UNIVERSE = MARKETDATA / "universe/a_share.parquet"
CALENDAR = MARKETDATA / "calendar/calendar_all_a.parquet"
INDEX_DIR = MARKETDATA / "index"

BAR_FIELDS = ("open", "high", "low", "close", "volume", "amount", "turnover")
UNADJ_FIELDS = ("open", "high", "low", "close")
VAL_FIELDS = (
    "pe_ttm",
    "pb_mrq",
    "pcf_ocf_ttm",
    "dividend_yield_ttm",
    "float_mv",
    "total_mv",
    "total_shares",
)
STATUS_FIELDS = ("listed_status", "up_down_status")
SW_FIELDS = ("sw_l1", "sw_l3")


def database_url() -> str:
    url = env("DATABASE_URL", "") or ""
    if not url:
        raise SystemExit("backend/.env 缺少 DATABASE_URL")
    return url


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _read(path: Path, columns: list[str]) -> pd.DataFrame:
    table = pq.read_table(path, columns=columns, use_pandas_metadata=False)
    return table.to_pandas(ignore_metadata=True)


def _col(symbol: str, field: str) -> str:
    return f"('{symbol}', '{field}')"


def _csv_rows_to_copy(conn: psycopg.Connection, table: str, columns: tuple[str, ...], rows: list[tuple]) -> int:
    if not rows:
        return 0
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerows(rows)
    buf.seek(0)
    with conn.cursor() as cur:
        with cur.copy(
            f"COPY {table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv, NULL '')"
        ) as copy:
            copy.write(buf.getvalue())
    return len(rows)


def _batch(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _symbols_from_universe() -> list[str]:
    df = _read(UNIVERSE, ["thscode", "name"])
    return [str(x) for x in df["thscode"].tolist() if x]


def _ensure_ref(conn: psycopg.Connection, from_date: date) -> None:
    log("ref_security / ref_trading_calendar / ref_industry")
    uni = _read(UNIVERSE, ["thscode", "name"]).fillna("")
    latest_status: dict[str, str] = {}
    latest_sw: dict[str, str] = {}
    # 取最后一个交易日的状态与行业，作为主数据快照；按批读取，保留每只的最后非空值
    symbols = [str(x) for x in uni["thscode"].tolist() if x]
    for batch in _batch(symbols, 300):
        cols = ["date"]
        for s in batch:
            cols.append(_col(s, "ths_listed_status_stock"))
            cols.append(_col(s, "ths_the_sw_industry_code_stock"))
        df = _read(VALUATION, cols)
        if df.empty:
            continue
        last = df.iloc[-1]
        for s in batch:
            st = last.get(_col(s, "ths_listed_status_stock"))
            sw = last.get(_col(s, "ths_the_sw_industry_code_stock"))
            if isinstance(st, str) and st:
                latest_status[s] = st
            if isinstance(sw, str) and sw:
                latest_sw[s] = sw

    # 行情首末日用于 list/delist；通过逐批读取首末日
    first_last: dict[str, tuple[str, str]] = {}
    for batch in _batch(symbols, 300):
        cols = ["date"] + [_col(s, "close") for s in batch]
        df = _read(HFQ, cols)
        for s in batch:
            series = df[["date", _col(s, "close")]].dropna()
            if series.empty:
                continue
            first_last[s] = (str(series["date"].iloc[0])[:10], str(series["date"].iloc[-1])[:10])

    def board(sym: str) -> str:
        code = sym.split(".")[0]
        if code.startswith(("688", "689")):
            return "STAR"
        if code.startswith(("300", "301")):
            return "ChiNext"
        if code.startswith(("8", "4")):
            return "BSE"
        if sym.endswith(".SH"):
            return "SH_MAIN"
        if sym.endswith(".SZ"):
            return "SZ_MAIN"
        return "OTHER"

    rows = []
    for sym, name in zip(uni["thscode"], uni["name"]):
        sym = str(sym)
        if not sym:
            continue
        status_raw = latest_status.get(sym, "在市")
        status = "delisted" if any(k in status_raw for k in ("终止", "退市")) else "listed"
        fd, ld = first_last.get(sym, (None, None))
        rows.append(
            (
                sym,
                str(name) or None,
                "CN",
                sym.split(".")[-1] if "." in sym else None,
                board(sym),
                fd,
                ld if status == "delisted" else None,
                status,
                "ifind",
            )
        )
    with conn.cursor() as cur:
        cur.execute("TRUNCATE ref_security")
        with cur.copy(
            "COPY ref_security (symbol,name,market,exchange,board,list_date,delist_date,status,source) "
            "FROM STDIN WITH (FORMAT csv, NULL '')"
        ) as copy:
            buf = io.StringIO()
            csv.writer(buf, lineterminator="\n").writerows(rows)
            buf.seek(0)
            copy.write(buf.getvalue())

    # 交易日历
    cal = _read(CALENDAR, ["date", "is_trade_day"])
    cal = cal.dropna(subset=["date"])
    cal_rows = [
        ("CN", str(d)[:10], str(bool(v)).lower(), "ifind")
        for d, v in zip(cal["date"], cal["is_trade_day"])
    ]
    # 去重
    cal_rows = list({(r[1]): r for r in cal_rows}.values())
    with conn.cursor() as cur:
        cur.execute("TRUNCATE ref_trading_calendar")
        with cur.copy(
            "COPY ref_trading_calendar (market,trade_date,is_open,source) FROM STDIN WITH (FORMAT csv, NULL '')"
        ) as copy:
            buf = io.StringIO()
            csv.writer(buf, lineterminator="\n").writerows(cal_rows)
            buf.seek(0)
            copy.write(buf.getvalue())

    # 申万一级行业（只有代码，名称待补）
    ind_rows = [(code, 1, None, None, "ifind") for code in sorted(set(latest_sw.values()))]
    with conn.cursor() as cur:
        cur.execute("TRUNCATE ref_industry")
        if ind_rows:
            with cur.copy(
                "COPY ref_industry (industry_code,level,name,parent_code,source) FROM STDIN WITH (FORMAT csv, NULL '')"
            ) as copy:
                buf = io.StringIO()
                csv.writer(buf, lineterminator="\n").writerows(ind_rows)
                buf.seek(0)
                copy.write(buf.getvalue())
    conn.commit()
    log(f"ref_security={len(rows)} calendar={len(cal_rows)} industry={len(ind_rows)}")


def _load_bars(conn: psycopg.Connection, from_date: date, batch_symbols: int) -> None:
    symbols = _symbols_from_universe()
    total = 0
    for bi, batch in enumerate(_batch(symbols, batch_symbols), 1):
        cols = ["date"]
        for s in batch:
            for f in BAR_FIELDS:
                cols.append(_col(s, f))
        df = _read(HFQ, cols)
        df = df[df["date"] >= from_date.isoformat()]
        rows = []
        for s in batch:
            sub = df[["date"] + [_col(s, f) for f in BAR_FIELDS]].copy()
            sub.columns = ["date"] + list(BAR_FIELDS)
            sub = sub.dropna(subset=["date"]).sort_values("date")
            if sub.empty:
                continue
            prev = None
            for r in sub.itertuples(index=False):
                close = None if pd.isna(r.close) else float(r.close)
                rows.append(
                    (
                        s,
                        str(r.date)[:10],
                        _f(r.open),
                        _f(r.high),
                        _f(r.low),
                        _f(close),
                        _f(prev),
                        _f(r.volume),
                        _f(r.amount),
                        _f(r.turnover),
                        "hfq",
                        "ifind",
                    )
                )
                prev = close
        with conn.cursor() as cur:
            cur.execute("DELETE FROM md_daily_bar WHERE adjust='hfq' AND symbol = ANY(%s)", (batch,))
        total += _csv_rows_to_copy(
            conn,
            "md_daily_bar",
            ("symbol", "trade_date", "open", "high", "low", "close", "pre_close", "volume", "amount", "turnover", "adjust", "source"),
            rows,
        )
        conn.commit()
        log(f"md_daily_bar hfq batch {bi} {batch[0]}..{batch[-1]} rows={len(rows)} total={total}")
    log(f"md_daily_bar hfq total={total}")


def _load_unadjusted(conn: psycopg.Connection, from_date: date, batch_symbols: int) -> None:
    symbols = _symbols_from_universe()
    total = 0
    for bi, batch in enumerate(_batch(symbols, batch_symbols), 1):
        cols = ["date"]
        for s in batch:
            for f in UNADJ_FIELDS:
                cols.append(_col(s, f))
        df = _read(UNADJ, cols)
        df = df[df["date"] >= from_date.isoformat()]
        rows = []
        for s in batch:
            sub = df[["date"] + [_col(s, f) for f in UNADJ_FIELDS]].copy()
            sub.columns = ["date"] + list(UNADJ_FIELDS)
            sub = sub.dropna(subset=["date"]).sort_values("date")
            prev = None
            for r in sub.itertuples(index=False):
                close = None if pd.isna(r.close) else float(r.close)
                rows.append(
                    (
                        s,
                        str(r.date)[:10],
                        _f(r.open),
                        _f(r.high),
                        _f(r.low),
                        _f(close),
                        _f(prev),
                        None,
                        None,
                        None,
                        "none",
                        "ifind",
                    )
                )
                prev = close
        with conn.cursor() as cur:
            cur.execute("DELETE FROM md_daily_bar WHERE adjust='none' AND symbol = ANY(%s)", (batch,))
        total += _csv_rows_to_copy(
            conn,
            "md_daily_bar",
            ("symbol", "trade_date", "open", "high", "low", "close", "pre_close", "volume", "amount", "turnover", "adjust", "source"),
            rows,
        )
        conn.commit()
        log(f"md_daily_bar none batch {bi} rows={len(rows)} total={total}")
    log(f"md_daily_bar none total={total}")


def _load_valuation_status(conn: psycopg.Connection, from_date: date, batch_symbols: int) -> None:
    symbols = _symbols_from_universe()
    vtotal = stotal = 0
    for bi, batch in enumerate(_batch(symbols, batch_symbols), 1):
        cols = ["date"]
        for s in batch:
            for f in (
                "ths_pe_ttm_stock",
                "ths_pb_mrq_stock",
                "ths_pcf_operating_cash_flow_ttm_stock",
                "ths_dividend_yield_ttm_stock",
                "ths_current_mv_stock",
                "ths_listed_status_stock",
                "ths_up_and_down_status_stock",
            ):
                cols.append(_col(s, f))
        df = _read(VALUATION, cols)
        df = df[df["date"] >= from_date.isoformat()]
        vrows, srows = [], []
        for s in batch:
            mapping = {
                "pe_ttm": "ths_pe_ttm_stock",
                "pb_mrq": "ths_pb_mrq_stock",
                "pcf_ocf_ttm": "ths_pcf_operating_cash_flow_ttm_stock",
                "dividend_yield_ttm": "ths_dividend_yield_ttm_stock",
                "float_mv": "ths_current_mv_stock",
                "listed_status": "ths_listed_status_stock",
                "up_down_status": "ths_up_and_down_status_stock",
            }
            sub = df[["date"] + [_col(s, f) for f in mapping.values()]].copy()
            sub.columns = ["date"] + list(mapping.keys())
            sub = sub.dropna(subset=["date"]).sort_values("date")
            for r in sub.itertuples(index=False):
                d = str(r.date)[:10]
                vrows.append(
                    (
                        s,
                        d,
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
                listed = r.listed_status if isinstance(r.listed_status, str) else None
                updown = r.up_down_status if isinstance(r.up_down_status, str) else None
                srows.append(
                    (
                        s,
                        d,
                        listed,
                        updown,
                        bool(listed and "ST" in listed),
                        updown == "停牌",
                        None,
                        None,
                        "ifind",
                    )
                )
        with conn.cursor() as cur:
            cur.execute("DELETE FROM md_valuation_daily WHERE symbol = ANY(%s)", (batch,))
            cur.execute("DELETE FROM md_status_daily WHERE symbol = ANY(%s)", (batch,))
        vtotal += _csv_rows_to_copy(
            conn,
            "md_valuation_daily",
            ("symbol", "trade_date", "pe_ttm", "pb_mrq", "pcf_ocf_ttm", "dividend_yield_ttm", "float_mv", "total_mv", "total_shares", "source"),
            vrows,
        )
        stotal += _csv_rows_to_copy(
            conn,
            "md_status_daily",
            ("symbol", "trade_date", "listed_status", "up_down_status", "is_st", "is_suspended", "limit_up", "limit_down", "source"),
            srows,
        )
        conn.commit()
        log(f"valuation/status batch {bi} rows={len(vrows)} totals={vtotal}/{stotal}")
    log(f"md_valuation_daily={vtotal} md_status_daily={stotal}")


def _load_index(conn: psycopg.Connection) -> None:
    log("index bars/members")
    index_files = sorted(INDEX_DIR.glob("index_price/*.parquet"))
    rows = []
    for p in index_files:
        code = p.stem.replace("index_price_", "")
        df = _read(p, ["date", "open", "high", "low", "close"])
        for r in df.itertuples(index=False):
            rows.append((code, str(r.date)[:10], _f(r.open), _f(r.high), _f(r.low), _f(r.close), None, None, "ifind"))
    with conn.cursor() as cur:
        cur.execute("TRUNCATE md_index_bar")
    _csv_rows_to_copy(
        conn,
        "md_index_bar",
        ("index_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "source"),
        rows,
    )
    with conn.cursor() as cur:
        cur.execute("TRUNCATE ref_index")
        cur.execute(
            "INSERT INTO ref_index (index_code,name,market,source) VALUES "
            "('000300.SH','沪深300','CN','ifind'),('000905.SH','中证500','CN','ifind') "
            "ON CONFLICT (index_code) DO NOTHING"
        )
    # 只载入最新快照 + 每月首个快照，避免 1000 万行权重历史
    member_rows = []
    for p in sorted(INDEX_DIR.glob("index_weights/*.parquet")):
        code = p.stem.replace("index_weights_", "")
        table = pq.read_table(p, use_pandas_metadata=False)
        df = table.to_pandas(ignore_metadata=True)
        if "date" not in df.columns:
            continue
        df = df.sort_values("date")
        months = df["date"].astype(str).str[:7]
        first_of_month = ~months.duplicated()
        latest = pd.Series(False, index=df.index)
        latest.iloc[-1] = True
        keep = df[first_of_month | latest]
        symbol_cols = [c for c in df.columns if c != "date"]
        for _, row in keep.iterrows():
            d = str(row["date"])[:10]
            for col in symbol_cols:
                val = row[col]
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    continue
                member_rows.append((code, str(col), d, None, float(val), "ifind"))
    with conn.cursor() as cur:
        cur.execute("TRUNCATE ref_index_member")
    _csv_rows_to_copy(
        conn,
        "ref_index_member",
        ("index_code", "symbol", "effective_from", "effective_to", "weight", "source"),
        member_rows,
    )
    conn.commit()
    log(f"md_index_bar={len(rows)} ref_index_member={len(member_rows)}")


def _load_industry_intervals(conn: psycopg.Connection, from_date: date, batch_symbols: int) -> None:
    """把个股申万一级行业按变化点压成区间，支持点时查询。"""
    log("ref_security_industry intervals")
    symbols = _symbols_from_universe()
    rows = []
    for bi, batch in enumerate(_batch(symbols, 300), 1):
        cols = ["date"]
        for s in batch:
            cols.append(_col(s, "ths_the_sw_industry_code_stock"))
        df = _read(VALUATION, cols)
        df = df[df["date"] >= from_date.isoformat()].sort_values("date")
        for s in batch:
            sub = df[["date", _col(s, "ths_the_sw_industry_code_stock")]].copy()
            sub.columns = ["date", "code"]
            sub = sub.dropna(subset=["date"])
            sub["code"] = sub["code"].ffill()
            if sub.empty:
                continue
            cur_code = None
            start = None
            for d, code in zip(sub["date"], sub["code"]):
                code = code if isinstance(code, str) and code else None
                if code != cur_code:
                    if cur_code and start:
                        rows.append((s, cur_code, 1, start, str(d)[:10], "ifind"))
                    cur_code = code
                    start = str(d)[:10]
            if cur_code and start:
                rows.append((s, cur_code, 1, start, None, "ifind"))
        log(f"industry intervals batch {bi} rows={len(rows)}")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE ref_security_industry")
    _csv_rows_to_copy(
        conn,
        "ref_security_industry",
        ("symbol", "industry_code", "level", "effective_from", "effective_to", "source"),
        rows,
    )
    conn.commit()
    log(f"ref_security_industry={len(rows)}")


def _f(v) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, float):
        return repr(v)
    return str(v)


def main() -> None:
    if os.environ.get("ALLOW_LEGACY_COLLECT") != "1":
        raise SystemExit(
            "该采集脚本已迁移到独立数据平台 /home/dev01/project/svquant-data；"
            "如确需应急运行，设置 ALLOW_LEGACY_COLLECT=1。"
        )
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default="2016-01-01")
    ap.add_argument("--batch-symbols", type=int, default=200)
    ap.add_argument("--truncate", action="store_true")
    ap.add_argument("--skip-bars", action="store_true")
    ap.add_argument("--skip-unadjusted", action="store_true")
    ap.add_argument("--skip-valuation", action="store_true")
    ap.add_argument("--skip-index", action="store_true")
    ap.add_argument("--skip-industry", action="store_true")
    ap.add_argument("--only-ref", action="store_true")
    args = ap.parse_args()
    from_date = date.fromisoformat(args.from_date)

    ensure_marketdata_schema(include_indexes=False)
    with psycopg.connect(database_url(), autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingest_run (job, source, status) VALUES ('etl_marketdata','ifind','running') RETURNING run_id"
            )
            run_id = cur.fetchone()[0]
        conn.commit()
        started = time.time()
        try:
            _ensure_ref(conn, from_date)
            if args.only_ref:
                pass
            else:
                if not args.skip_bars:
                    _load_bars(conn, from_date, args.batch_symbols)
                if not args.skip_unadjusted:
                    _load_unadjusted(conn, from_date, args.batch_symbols)
                if not args.skip_valuation:
                    _load_valuation_status(conn, from_date, args.batch_symbols)
                if not args.skip_index:
                    _load_index(conn)
                if not args.skip_industry:
                    _load_industry_intervals(conn, from_date, args.batch_symbols)
            ensure_marketdata_indexes()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE ingest_run SET status='success', finished_at=NOW(), detail=%s WHERE run_id=%s",
                    (json.dumps({"from": from_date.isoformat(), "seconds": round(time.time() - started, 1)}, ensure_ascii=False), run_id),
                )
                cur.execute(
                    "INSERT INTO ingest_watermark (job,source,last_success_at,last_data_date) "
                    "VALUES ('etl_marketdata','ifind',NOW(),%s) "
                    "ON CONFLICT (job,source) DO UPDATE SET last_success_at=NOW(), last_data_date=EXCLUDED.last_data_date",
                    (date.today(),),
                )
            conn.commit()
            log(f"done in {time.time() - started:.1f}s")
        except Exception as exc:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE ingest_run SET status='failed', finished_at=NOW(), error=%s WHERE run_id=%s",
                    (str(exc)[:2000], run_id),
                )
            conn.commit()
            raise


if __name__ == "__main__":
    main()
