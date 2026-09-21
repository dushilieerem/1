# -*- coding: utf-8 -*-
"""补算面板里 Q1/Q5 为空的组合（analysis_level=full）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.daily_dashboard_refresh import run_one  # noqa: E402
from services.factor import dashboard_store as ds  # noqa: E402
from services.core.db import get_conn  # noqa: E402


def combos_needing_backfill() -> list[tuple[str, str, bool]]:
    ds.migrate_legacy_factor_dashboard_metrics()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT universe, period, filter_limit_up
            FROM factor_dashboard_metrics
            GROUP BY 1, 2, 3
            HAVING SUM(
              CASE WHEN (error IS NULL OR error='') AND q1_return IS NULL
                   THEN 1 ELSE 0 END
            ) > 0
            ORDER BY universe, period, filter_limit_up DESC
            """
        ).fetchall()
    return [
        (str(row["universe"]), str(row["period"]), bool(row["filter_limit_up"]))
        for row in rows
    ]


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
