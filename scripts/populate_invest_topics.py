#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""为 H5 的 3 个示例主题补齐成分股与等权走势。

主题当前是产品种子（AI 算力 / 高股息 / 新能源），本脚本维护其成分股，
并从 md_daily_bar(hfq) 计算等权归一化指数写入 invest_topic_bars。

  DATABASE_URL=... /home/dev01/program/anaconda3/bin/python scripts/populate_invest_topics.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.invest.schema import ensure_invest_schema  # noqa: E402

TOPICS: dict[str, list[str]] = {
    "ai": ["688256", "603019", "000977", "002463", "600183", "002916", "300442", "002837"],
    "dividend": ["601398", "601939", "601288", "601988", "600036", "601088", "600900", "601857"],
    "new-energy": ["300750", "002594", "601012", "300274", "300014", "002459", "002812", "600795"],
}
LOOKBACK = 120


def main() -> int:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("需要 DATABASE_URL")
    ensure_invest_schema()
    with psycopg.connect(url, row_factory=psycopg.rows.dict_row) as conn:
        for topic_id, codes in TOPICS.items():
            for code in codes:
                conn.execute(
                    """
                    INSERT INTO invest_topic_stocks (topic_id, code)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """,
                    (topic_id, code),
                )
            dates = [
                r["trade_date"]
                for r in conn.execute(
                    """
                    SELECT DISTINCT trade_date FROM md_daily_bar
                     WHERE adjust='hfq' AND split_part(symbol, '.', 1) = ANY(%s)
                     ORDER BY trade_date DESC LIMIT %s
                    """,
                    (codes, LOOKBACK),
                ).fetchall()
            ]
            if len(dates) < 2:
                print(f"[{topic_id}] 日线不足，跳过")
                continue
            rows = conn.execute(
                """
                SELECT split_part(symbol, '.', 1) AS code, trade_date, close
                  FROM md_daily_bar
                 WHERE adjust='hfq' AND split_part(symbol, '.', 1) = ANY(%s)
                   AND trade_date >= %s
                """,
                (codes, min(dates)),
            ).fetchall()
            by_code: dict[str, dict] = {}
            for r in rows:
                by_code.setdefault(r["code"], {})[r["trade_date"]] = float(r["close"])
            series: list[tuple] = []
            for d in sorted(dates):
                vals = []
                for code in codes:
                    closes = by_code.get(code) or {}
                    if d in closes:
                        vals.append(closes[d])
                if vals:
                    series.append((d, sum(vals) / len(vals)))
            if len(series) < 60:
                print(f"[{topic_id}] 等权序列不足 60，跳过")
                continue
            base = series[0][1]
            for d, value in series:
                conn.execute(
                    """
                    INSERT INTO invest_topic_bars (topic_id, date, close, turnover, valuation)
                    VALUES (%s, %s, %s, NULL, NULL)
                    ON CONFLICT (topic_id, date) DO UPDATE SET close = EXCLUDED.close
                    """,
                    (topic_id, d.isoformat(), round(value / base * 100, 4)),
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
