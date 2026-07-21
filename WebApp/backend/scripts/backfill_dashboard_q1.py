# -*- coding: utf-8 -*-
"""补算面板里 Q1/Q5 为空的组合（analysis_level=full）。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.daily_dashboard_refresh import run_one  # noqa: E402
from services.dashboard_store import DB_PATH  # noqa: E402


def combos_needing_backfill() -> list[tuple[str, str, bool]]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT universe, period, filter_limit_up,
               SUM(CASE WHEN (error IS NULL OR error='') AND q1_return IS NULL THEN 1 ELSE 0 END) AS empty_q1
        FROM factor_dashboard_metrics
        GROUP BY 1, 2, 3
        HAVING empty_q1 > 0
        ORDER BY universe, period, filter_limit_up DESC
        """
    ).fetchall()
    conn.close()
    return [(u, p, bool(f)) for u, p, f, _ in rows]


def main() -> None:
    jobs = combos_needing_backfill()
    print(f"backfill combos={len(jobs)}")
    for i, (u, p, f) in enumerate(jobs, 1):
        print(f"  [{i}/{len(jobs)}] {u} {p} filter_up={f}")
    failed = 0
    for u, p, f in jobs:
        job = run_one(u, p, filter_limit_up=f, limit=None)
        if job.get("status") == "failed":
            failed += 1
    print(f"backfill done failed={failed}/{len(jobs)}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
