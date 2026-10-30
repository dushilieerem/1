"""Live EOD ingestion using public Tencent/Eastmoney HTTP endpoints.

This is intentionally independent of AKShare: AKShare's endpoints failed in the
current environment (`RemoteDisconnected`), while the underlying Tencent/Eastmoney
HTTPS endpoints are reachable.  It is still a research/demo pipeline: verify
public-display/licensing terms before exposing the data.

Usage:
  conda run -n svquant python scripts/fetch_live.py --db data/live.db --codes 300750,600519
  conda run -n svquant python scripts/fetch_live.py --db data/live.db --codes all
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from bisect import bisect_left
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seed import DB_PATH, seed  # noqa: E402

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://gu.qq.com/",
}
TENCENT_K = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
EASTMONEY = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def sym(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return "sh" + code
    return "sz" + code


def get_json(url: str, params: dict | None = None, timeout: int = 25) -> dict:
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            time.sleep(1 + attempt)
    raise RuntimeError(str(last))


def fetch_bars(code: str) -> list[tuple]:
    data = get_json(TENCENT_K, {"param": f"{sym(code)},day,,,800,qfq"})
    node = (data.get("data") or {}).get(sym(code)) or {}
    rows = node.get("qfqday") or node.get("day") or []
    out = []
    for row in rows:
        if len(row) < 6:
            continue
        out.append((code, str(row[0])[:10], float(row[1]), float(row[3]), float(row[4]),
                    float(row[2]), float(row[5]), float(row[5]) * float(row[2]) * 100))
    return out


def fetch_valuations(code: str) -> list[tuple]:
    out = []
    for page in range(1, 8):
        payload = get_json(EASTMONEY, {
            "reportName": "RPT_VALUEANALYSIS_DET",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "pageNumber": page,
            "pageSize": 500,
            "sortColumns": "TRADE_DATE",
            "sortTypes": -1,
        })
        result = payload.get("result") or {}
        rows = result.get("data") or []
        if not rows:
            break
        for r in rows:
            pe = r.get("PE_TTM")
            pb = r.get("PB_MRQ")
            if pe is None or pb is None:
                continue
            out.append((code, str(r.get("TRADE_DATE"))[:10], float(pe), float(pb)))
        if len(rows) < 500:
            break
    return out


def fetch_financials(code: str) -> list[tuple]:
    payload = get_json(EASTMONEY, {
        "reportName": "RPT_LICO_FN_CPD",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": 1,
        "pageSize": 50,
        "sortColumns": "REPORTDATE",
        "sortTypes": -1,
    })
    rows = (payload.get("result") or {}).get("data") or []
    out = []
    for r in rows:
        period = r.get("QDATE")
        if not period or not r.get("REPORTDATE"):
            continue
        revenue = (r.get("TOTAL_OPERATE_INCOME") or 0) / 1e8
        profit = (r.get("PARENT_NETPROFIT") or 0) / 1e8
        report_date = str(r.get("NOTICE_DATE") or r.get("REPORTDATE"))[:10]
        gross = r.get("XSMLL") or 0
        roe = r.get("WEIGHTAVG_ROE") or 0
        yoy = r.get("YSTZ") or 0
        pyoy = r.get("SJLTZ") or 0
        out.append((code, period, round(revenue, 1), round(yoy, 1), round(profit, 1), round(pyoy, 1),
                    round(gross, 2), round(roe, 1), None, report_date))
    return out


def next_report(latest_period: str | None) -> str | None:
    if not latest_period or len(latest_period) < 6:
        return None
    year = int(latest_period[:4])
    q = latest_period[-1]
    if q == "1":
        return f"{year}-08-31"
    if q == "2":
        return f"{year}-10-31"
    if q == "3":
        return f"{year + 1}-03-31"
    return f"{year + 1}-04-30"


def fetch_index(conn: sqlite3.Connection, code: str, name: str) -> None:
    sym = ("sh" if code.startswith("0") else "sz") + code
    data = get_json(TENCENT_K, {"param": f"{sym},day,,,5,qfq"})
    node = (data.get("data") or {}).get(sym) or {}
    rows = node.get("qfqday") or node.get("day") or []
    if len(rows) < 2:
        raise RuntimeError("no index bars")
    last, prev = rows[-1], rows[-2]
    conn.execute("INSERT OR REPLACE INTO indices VALUES (?,?,?,?,?)",
                 (code, name, float(last[2]), float(prev[2]), f"{str(last[0])[:10]} 18:30:00"))
    conn.commit()
    print(f"[index {code}] {name} {last[2]} (prev {prev[2]})")


def update_betas(conn: sqlite3.Connection) -> None:
    """Real 1y beta vs CSI300 from daily bars; clamps extreme values."""
    data = get_json(TENCENT_K, {"param": "sh000300,day,,,320,qfq"})
    node = (data.get("data") or {}).get("sh000300") or {}
    rows = node.get("qfqday") or node.get("day") or []
    bench = {str(r[0])[:10]: float(r[2]) for r in rows}
    if len(bench) < 80:
        print("[beta] skipped: insufficient benchmark")
        return
    updated = 0
    for stock in conn.execute("SELECT code FROM stocks WHERE asset='stock'").fetchall():
        code = stock["code"]
        bars = conn.execute("SELECT date, close FROM bars WHERE code=? ORDER BY date ASC", (code,)).fetchall()
        by_date = {r["date"]: float(r["close"]) for r in bars}
        common = sorted(set(by_date) & set(bench))
        if len(common) < 80:
            continue
        rs, ri = [], []
        for prev, cur in zip(common, common[1:]):
            rs.append(by_date[cur] / by_date[prev] - 1)
            ri.append(bench[cur] / bench[prev] - 1)
        mean_s = sum(rs) / len(rs)
        mean_i = sum(ri) / len(ri)
        cov = sum((a - mean_s) * (b - mean_i) for a, b in zip(rs, ri)) / len(rs)
        var = sum((b - mean_i) ** 2 for b in ri) / len(ri)
        if var <= 0:
            continue
        beta = max(0.2, min(2.2, cov / var))
        conn.execute("UPDATE stocks SET beta=? WHERE code=?", (round(beta, 2), code))
        updated += 1
    conn.commit()
    print(f"[beta] updated {updated} stocks vs CSI300")


def rebuild_topics(conn: sqlite3.Connection) -> None:
    """Equal-weight proxy index from real constituents.

    Membership is editorial and must be reviewed before public launch.  The
    series, valuation percentiles and turnover proxy are derived from real EOD
    data, not the synthetic seed.
    """
    topics = conn.execute("SELECT id, name FROM topics").fetchall()
    for topic in topics:
        codes = [r["code"] for r in conn.execute(
            "SELECT code FROM topic_stocks WHERE topic_id=? ORDER BY code", (topic["id"],))]
        bars: dict[str, dict[str, sqlite3.Row]] = {}
        for code in codes:
            rows = conn.execute(
                "SELECT date, close, volume FROM bars WHERE code=? ORDER BY date DESC LIMIT 750", (code,)
            ).fetchall()
            rows = list(reversed(rows))
            if len(rows) >= 60:
                bars[code] = {r["date"]: r for r in rows}
        if len(bars) < 2:
            print(f"[topic {topic['id']}] skipped: insufficient bars")
            continue
        common = sorted(set.intersection(*[set(v) for v in bars.values()]))
        if len(common) < 60:
            print(f"[topic {topic['id']}] skipped: no common dates")
            continue
        first = common[0]
        val_pct: dict[str, dict[str, float]] = {}
        for code in bars:
            rows = conn.execute(
                "SELECT date, pe_ttm FROM valuations WHERE code=? AND pe_ttm IS NOT NULL "
                "ORDER BY date DESC LIMIT 750", (code,)
            ).fetchall()
            pe = [float(r["pe_ttm"]) for r in rows]
            if not pe:
                continue
            pe_sorted = sorted(pe)
            val_pct[code] = {r["date"]: bisect_left(pe_sorted, float(r["pe_ttm"])) / len(pe_sorted) * 100
                             for r in rows}
        turn_by: dict[str, dict[str, float]] = {}
        for code, by_date in bars.items():
            seq = [by_date[d] for d in common]
            vols = [float(r["volume"] or 0) for r in seq]
            out = {}
            for i, d in enumerate(common):
                window = vols[max(0, i - 19): i + 1]
                avg = sum(window) / len(window) if window else 0
                out[d] = min(100.0, max(0.0, (vols[i] / avg * 50) if avg else 0))
            turn_by[code] = out
        rows = []
        for d in common:
            closes = [bars[c][d]["close"] / bars[c][first]["close"] * 1000 for c in bars]
            turns = [turn_by[c][d] for c in bars]
            vals = [val_pct[c][d] for c in bars if c in val_pct and d in val_pct[c]]
            rows.append((topic["id"], d, round(sum(closes) / len(closes), 2),
                         round(sum(turns) / len(turns), 1),
                         round(sum(vals) / len(vals), 1) if vals else None))
        conn.execute("DELETE FROM topic_bars WHERE topic_id=?", (topic["id"],))
        conn.executemany("INSERT INTO topic_bars VALUES (?,?,?,?,?)", rows)
        last = rows[-1]
        heat = round((last[3] + (last[4] or 0)) / 2, 1)
        conn.execute("UPDATE topics SET heat=?, valuation_percentile=?, turnover_percentile=?, updated_at=? WHERE id=?",
                     (heat, last[4], last[3], f"{last[1]} 18:30:00", topic["id"]))
        conn.commit()
        print(f"[topic {topic['id']}] {topic['name']} bars={len(rows)} val={last[4]} turn={last[3]}")


def ingest(conn: sqlite3.Connection, code: str) -> None:
    bars = fetch_bars(code)
    if not bars:
        raise RuntimeError("no bars")
    conn.execute("DELETE FROM bars WHERE code=?", (code,))
    conn.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?)", bars)
    last, prev = bars[-1], bars[-2] if len(bars) > 1 else bars[-1]

    vals = fetch_valuations(code) if not code.startswith(("5", "1")) else []
    if vals:
        conn.execute("DELETE FROM valuations WHERE code=?", (code,))
        conn.executemany("INSERT OR REPLACE INTO valuations VALUES (?,?,?,?)", vals)
    else:
        conn.execute("DELETE FROM valuations WHERE code=?", (code,))
    latest_val = vals[0] if vals else None

    fins = fetch_financials(code) if not code.startswith(("5", "1")) else []
    if fins:
        conn.execute("DELETE FROM financials WHERE code=?", (code,))
        conn.executemany("INSERT OR REPLACE INTO financials VALUES (?,?,?,?,?,?,?,?,?,?)", fins)
    else:
        conn.execute("DELETE FROM financials WHERE code=?", (code,))

    pe = latest_val[2] if latest_val else None
    pb = latest_val[3] if latest_val else None
    # The valuation endpoint has market cap/shares; use a light second query only
    # for the latest row so we can update market cap/turnover.
    mcap = None
    shares = None
    if latest_val:
        try:
            payload = get_json(EASTMONEY, {
                "reportName": "RPT_VALUEANALYSIS_DET", "columns": "ALL",
                "filter": f'(SECURITY_CODE="{code}")', "pageNumber": 1, "pageSize": 1,
                "sortColumns": "TRADE_DATE", "sortTypes": -1,
            })
            row = ((payload.get("result") or {}).get("data") or [None])[0]
            if row:
                mcap = row.get("TOTAL_MARKET_CAP")
                shares = row.get("TOTAL_SHARES")
        except Exception:
            pass
    turnover = None
    if shares:
        turnover = float(last[6]) * 100 / float(shares) * 100
    conn.execute(
        "UPDATE stocks SET price=?, prev_close=?, open=?, high=?, low=?, volume=?, amount=?, "
        "market_cap=?, pe_ttm=?, pb=?, turnover=?, next_report_date=?, updated_at=? WHERE code=?",
        (last[5], prev[5], last[2], last[3], last[4], last[6], last[7], mcap, pe, pb,
         round(turnover, 2) if turnover is not None else None,
         next_report(fins[0][1] if fins else None), f"{last[1]} 18:30:00", code),
    )
    conn.commit()
    print(f"[{code}] bars={len(bars)} vals={len(vals)} fins={len(fins)} last={last[1]} close={last[5]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None)
    parser.add_argument("--codes", default="all")
    args = parser.parse_args()
    path = Path(args.db) if args.db else DB_PATH
    if not path.exists():
        seed(force=True)
        if path != DB_PATH:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(DB_PATH, path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    if args.codes == "all":
        codes = [r["code"] for r in conn.execute("SELECT code FROM stocks").fetchall()]
    else:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    ok = 0
    for code in codes:
        try:
            ingest(conn, code)
            ok += 1
        except Exception as exc:
            print(f"[{code}] failed: {exc}")
    try:
        fetch_index(conn, "000300", "沪深 300")
        fetch_index(conn, "399006", "创业板指")
    except Exception as exc:
        print(f"[index] failed: {exc}")
    try:
        update_betas(conn)
    except Exception as exc:
        print(f"[beta] failed: {exc}")
    try:
        rebuild_topics(conn)
    except Exception as exc:
        print(f"[topic] failed: {exc}")
    if ok:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('source', 'live')")
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('updated_at', ?)", (f"{date.today().isoformat()} 18:30:00",))
        conn.commit()
    conn.close()
    print(f"done {ok}/{len(codes)}; topics/news remain demo unless separately ingested.")


if __name__ == "__main__":
    main()
