"""AKShare EOD ingestion scaffold (NOT production-verified).

What it does
- Pulls qfq daily bars for a list of A-share codes and upserts `bars`.
- Updates the latest quote fields in `stocks`.
- Optionally refreshes a full-market snapshot for name/PE/PB/market cap.
- Leaves financials/valuations as the seeded demo values; those need a
  separate quarterly/financial ingestion job.

Usage
  conda run -n svquant python scripts/fetch_akshare.py --codes 300750,600519 --start 2023-01-01
  conda run -n svquant python scripts/fetch_akshare.py --spot

Important
- AKShare aggregates upstream sites; verify public-display/commercial terms
  before exposing the data.  This script is for local evaluation only.
- Endpoints can hang or change; production needs timeouts, retries, alerts.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seed import DB_PATH, seed  # noqa: E402


def _connect(db: str | None) -> sqlite3.Connection:
    path = Path(db) if db else DB_PATH
    if not path.exists():
        seed(force=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_bars(conn: sqlite3.Connection, code: str, start: str) -> int:
    import akshare as ak

    df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start.replace("-", ""),
                            end_date=date.today().strftime("%Y%m%d"), adjust="qfq")
    if df is None or df.empty:
        print(f"[{code}] empty")
        return 0
    count = 0
    rows = []
    for _, r in df.iterrows():
        rows.append((
            code, str(r["日期"])[:10], float(r["开盘"]), float(r["最高"]), float(r["最低"]),
            float(r["收盘"]), float(r["成交量"]), float(r["成交额"]),
        ))
    conn.executemany("INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?,?)", rows)
    last = rows[-1]
    prev = rows[-2][5] if len(rows) > 1 else last[5]
    conn.execute(
        "UPDATE stocks SET price=?, prev_close=?, open=?, high=?, low=?, volume=?, amount=?, updated_at=? WHERE code=?",
        (last[5], prev, last[2], last[3], last[4], last[6], last[7], f"{last[1]} 18:30:00", code),
    )
    count = len(rows)
    conn.commit()
    print(f"[{code}] bars={count} last={last[1]} close={last[5]}")
    return count


def fetch_spot(conn: sqlite3.Connection) -> None:
    import akshare as ak

    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        print("spot empty")
        return
    wanted = {r["code"] for r in conn.execute("SELECT code FROM stocks").fetchall()}
    updated = 0
    for _, r in df.iterrows():
        code = str(r["代码"])
        if code not in wanted:
            continue
        conn.execute(
            "UPDATE stocks SET name=?, price=?, prev_close=?, open=?, high=?, low=?, "
            "market_cap=?, pe_ttm=?, pb=?, turnover=?, volume=?, amount=?, updated_at=? WHERE code=?",
            (str(r["名称"]), float(r["最新价"]), float(r["昨收"]), float(r["今开"]), float(r["最高"]),
             float(r["最低"]), float(r.get("总市值") or 0), float(r.get("市盈率-动态") or 0),
             float(r.get("市净率") or 0), float(r.get("换手率") or 0), float(r["成交量"]),
             float(r["成交额"]), f"{date.today().isoformat()} 18:30:00", code),
        )
        updated += 1
    conn.commit()
    print(f"spot updated={updated}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", default="300750,600519,600036,510300,300308,300014,002074,601318")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--db", default=None)
    parser.add_argument("--spot", action="store_true")
    args = parser.parse_args()

    conn = _connect(args.db)
    if args.spot:
        try:
            fetch_spot(conn)
        except Exception as exc:
            print(f"spot failed: {exc}")
    for code in [c.strip() for c in args.codes.split(",") if c.strip()]:
        try:
            fetch_bars(conn, code, args.start)
        except Exception as exc:
            print(f"[{code}] failed: {exc}")
    conn.close()
    print("done. financials/valuations remain demo values; wire a quarterly job before public use.")


if __name__ == "__main__":
    main()
