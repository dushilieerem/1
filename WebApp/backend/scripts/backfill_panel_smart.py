# -*- coding: utf-8 -*-
"""智能补算：只重跑「成功但无 Q1」或「瞬时失败 / 已知可修因子」。

「数据不可用」因子不调 RE，只靠 mark_unavailable_factors / index.yaml 标记，不编造。

用法:
  conda activate SVQuant
  cd /d E:\\quant-lab\\SV\\SVQuant\\WebApp\\backend
  python scripts/mark_unavailable_factors.py
  python scripts/backfill_panel_smart.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.daily_dashboard_refresh import MATRIX_24, log  # noqa: E402
from services.factor import dashboard_store as ds  # noqa: E402

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


def _is_transient_error(err: str | None) -> bool:
    e = (err or "").strip()
    if not e:
        return False
    if "数据不可用" in e:
        return False
    keys = (
        "timed out",
        "timeout",
        "urlopen",
        "WinError",
        "10051",
        "10054",
        "10061",
        "连接",
        "断开",
        "Remote",
        "502",
        "503",
        "504",
    )
    return any(k.lower() in e.lower() if k.isascii() else k in e for k in keys)


def names_needed(universe: str, period: str, filter_limit_up: bool) -> list[str]:
    conn = sqlite3.connect(ds.DB_PATH)
    rows = conn.execute(
        """
        SELECT factor_name, error, q1_return
        FROM factor_dashboard_metrics
        WHERE universe = ?
          AND period = ?
          AND filter_limit_up = ?
          AND filter_suspended = 1
          AND rules_version = ?
          AND factor_name != 'EDIT_BEFORE'
        ORDER BY 1
        """,
        [
            universe,
            period,
            1 if filter_limit_up else 0,
            ds.RULES_VERSION,
        ],
    ).fetchall()
    conn.close()

    needed: list[str] = []
    seen: set[str] = set()
    for name, err, q1 in rows:
        if name in UNAVAILABLE_SKIP:
            continue
        # 仅：缺 Q1 / 瞬时网络失败 / 可修因子且当前仍失败
        if (err is None or err == "") and q1 is None:
            pick = True
        elif _is_transient_error(err):
            pick = True
        elif name in FIXED_NAMES and err:
            pick = True
        else:
            pick = False
        if pick and name not in seen:
            seen.add(name)
            needed.append(name)
    return needed


def main() -> None:
    plan: list[tuple[str, str, bool, list[str]]] = []
    for u, p, f in MATRIX_24:
        names = names_needed(u, p, f)
        if names:
            plan.append((u, p, f, names))

    log(f"smart backfill combos={len(plan)} db={ds.DB_PATH}")
    for u, p, f, names in plan:
        log(
            f"  {u} {p} filter_up={f} names={len(names)} -> "
            f"{','.join(names[:12])}{'…' if len(names) > 12 else ''}"
        )

    if not plan:
        log("nothing to retry (miss_q1=0 and no transient errors)")
        raise SystemExit(0)

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
