# -*- coding: utf-8 -*-
"""智能补算：只重跑「成功但无 Q1」或「已知坏因子/有 error」的行。

比整组 82 因子全刷快很多。修代码后建议先停掉旧的整组 backfill，再跑本脚本。

用法:
  conda activate NBquant
  cd /d E:\\quant-lab\\SVQuant\\backend
  python scripts/backfill_panel_smart.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.daily_dashboard_refresh import MATRIX_24, log  # noqa: E402
from services import dashboard_store as ds  # noqa: E402

# 已修代码、可重算的因子（不含「数据不可用」——那些只标记不编造）
FIXED_NAMES = [
    "cvar_5",
    "macd_cross",
    "stoch_rsi",
    "gap",
    "volume_price_corr",
    "max_drawdown_20d",
]

# 缺字段：只标记、不调 RE
UNAVAILABLE_SKIP = {
    "ep",
    "cp_ttm",
    "dividend_yield",
    "dividend_cover",
    "peg",
    "ev_ebitda",
    "value_vs_growth",
}


def names_needed(universe: str, period: str, filter_limit_up: bool) -> list[str]:
    conn = sqlite3.connect(ds.DB_PATH)
    rows = conn.execute(
        """
        SELECT factor_name
        FROM factor_dashboard_metrics
        WHERE universe = ?
          AND period = ?
          AND filter_limit_up = ?
          AND filter_suspended = 1
          AND rules_version = ?
          AND factor_name != 'EDIT_BEFORE'
          AND (
                (error IS NOT NULL AND error != '')
             OR ((error IS NULL OR error = '') AND q1_return IS NULL)
             OR factor_name IN ({placeholders})
          )
        ORDER BY 1
        """.format(placeholders=",".join("?" * len(FIXED_NAMES))),
        [
            universe,
            period,
            1 if filter_limit_up else 0,
            ds.RULES_VERSION,
            *FIXED_NAMES,
        ],
    ).fetchall()
    conn.close()
    if not rows:
        return [
            f["name"]
            for f in ds.load_factor_index()
            if not f.get("unavailable") and f["name"] not in UNAVAILABLE_SKIP
        ]
    return [r[0] for r in rows if r[0] not in UNAVAILABLE_SKIP]


def main() -> None:
    plan: list[tuple[str, str, bool, list[str]]] = []
    for u, p, f in MATRIX_24:
        names = names_needed(u, p, f)
        if names:
            plan.append((u, p, f, names))

    log(f"smart backfill combos={len(plan)}")
    for u, p, f, names in plan:
        log(f"  {u} {p} filter_up={f} names={len(names)}")

    failed = 0
    for i, (u, p, f, names) in enumerate(plan, 1):
        log(f"=== [{i}/{len(plan)}] {u}/{p}/filter_up={f} only={len(names)} ===")
        ds._run_batch(
            universe=u,
            period=p,
            filter_limit_up=f,
            filter_suspended=True,
            limit=None,
            only_names=names,
        )
        job = ds.read_job()
        log(f"=== 结束 status={job.get('status')} error={job.get('error')} ===")
        if job.get("status") == "failed":
            failed += 1

    log(f"smart backfill done failed={failed}/{len(plan)}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
