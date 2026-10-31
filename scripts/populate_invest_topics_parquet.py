#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从本地 hfq parquet 直接补齐 H5 主题成分与等权走势（不依赖 PG 行数）。

  DATABASE_URL=... MARKETDATA_DIR=/home/dev01/project/marketdata \
    /home/dev01/program/anaconda3/bin/python scripts/populate_invest_topics_parquet.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.invest.schema import ensure_invest_schema  # noqa: E402

TOPICS = {
    "ai": ["688256", "603019", "000977", "002463", "600183", "002916", "300442", "002837"],
    "dividend": ["601398", "601939", "601288", "601988", "600036", "601088", "600900", "601857"],
    "new-energy": ["300750", "002594", "601012", "300274", "300014", "002459", "002812", "600795"],
}
LOOKBACK = 120


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    root = Path(os.environ.get("MARKETDATA_DIR", "/home/dev01/project/marketdata"))
    if not url:
        raise SystemExit("需要 DATABASE_URL")
    path = root / "market_data/market_data_hfq.parquet"
    names = pq.ParquetFile(path).schema_arrow.names
    close_cols: dict[str, str] = {}
    for name in names:
        if not name.startswith("('") or "', 'close')" not in name:
            continue
        symbol = name.split("'")[1]
        close_cols[symbol.split(".")[0]] = name
    wanted = sorted({c for codes in TOPICS.values() for c in codes if c in close_cols})
    cols = ["date"] + [close_cols[c] for c in wanted]
    table = pq.read_table(path, columns=cols).to_pydict()
    dates = table["date"]
    ensure_invest_schema()
    with psycopg.connect(url) as conn:
        for topic_id, codes in TOPICS.items():
            for code in codes:
                conn.execute(
                    "INSERT INTO invest_topic_stocks (topic_id, code) VALUES (%s,%s) "
                    "ON CONFLICT DO NOTHING",
                    (topic_id, code),
                )
            series = []
            for i, d in enumerate(dates):
                vals = []
                for code in codes:
                    col = close_cols.get(code)
                    if not col:
                        continue
                    v = table[col][i]
                    if v is not None:
                        vals.append(float(v))
                if vals:
                    series.append((str(d)[:10], sum(vals) / len(vals)))
            if len(series) < 60:
                print(f"[{topic_id}] series too short")
                continue
            series = series[-LOOKBACK:]
            base = series[0][1]
            for d, value in series:
                conn.execute(
                    "INSERT INTO invest_topic_bars (topic_id, date, close, turnover, valuation) "
                    "VALUES (%s,%s,%s,NULL,NULL) "
                    "ON CONFLICT (topic_id, date) DO UPDATE SET close=EXCLUDED.close",
                    (topic_id, d, round(value / base * 100, 4)),
                )
            conn.execute(
                "UPDATE invest_topics SET updated_at=%s WHERE id=%s",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), topic_id),
            )
            print(f"[{topic_id}] codes={len(codes)} bars={len(series)}")
        conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
