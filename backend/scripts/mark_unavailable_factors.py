# -*- coding: utf-8 -*-
"""把「数据不可用」因子的编造指标清掉，只保留明确 error 标记。"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factor.dashboard_store import (  # noqa: E402
    RULES_VERSION,
    migrate_legacy_factor_dashboard_metrics,
)
from services.core.db import get_conn  # noqa: E402

INDEX = ROOT / "factor" / "index.yaml"


def unavailable_from_index() -> dict[tuple[str, str], str]:
    raw = yaml.safe_load(INDEX.read_text(encoding="utf-8")) or {}
    out: dict[tuple[str, str], str] = {}
    for library_name, lib in (raw.get("libraries") or {}).items():
        for f in lib.get("factors") or []:
            if f.get("unavailable"):
                name = f.get("name")
                if name:
                    out[(str(library_name), str(name))] = (
                        f.get("unavailable_reason") or "数据不可用"
                    ).strip()
    return out


def main() -> None:
    reasons = unavailable_from_index()
    print("unavailable", list(reasons))
    migrate_legacy_factor_dashboard_metrics()
    total = 0
    with get_conn() as conn:
        for (library, name), reason in reasons.items():
            cur = conn.execute(
                """
                UPDATE factor_dashboard_metrics
                SET ic_mean=NULL, ic_std=NULL, ir=NULL, rank_ic=NULL,
                    q1_return=NULL, q5_return=NULL, long_short_spread=NULL,
                    turnover=NULL, q1_turnover=NULL, q5_turnover=NULL,
                    coverage_pool=NULL, coverage_total=NULL,
                    win_rate=NULL, volatility=NULL,
                    sharpe=NULL, annual_return=NULL, max_drawdown=NULL,
                    error=%s, computed_at=NOW()
                WHERE library=%s AND factor_name=%s AND rules_version=%s
                """,
                (reason[:500], library, name, RULES_VERSION),
            )
            print(f"  {library}/{name}: cleared {cur.rowcount} rows -> {reason}")
            total += cur.rowcount
    print(f"done total_rows={total}")


if __name__ == "__main__":
    main()
