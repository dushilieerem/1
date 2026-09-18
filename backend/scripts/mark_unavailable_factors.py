# -*- coding: utf-8 -*-
"""把「数据不可用」因子的编造指标清掉，只保留明确 error 标记。"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factor.dashboard_store import DB_PATH, RULES_VERSION  # noqa: E402

INDEX = ROOT / "factor" / "index.yaml"


def unavailable_from_index() -> dict[str, str]:
    raw = yaml.safe_load(INDEX.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for lib in (raw.get("libraries") or {}).values():
        for f in lib.get("factors") or []:
            if f.get("unavailable"):
                name = f.get("name")
                if name:
                    out[name] = (f.get("unavailable_reason") or "数据不可用").strip()
    return out


def main() -> None:
    reasons = unavailable_from_index()
    print("unavailable", list(reasons))
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    total = 0
    for name, reason in reasons.items():
        cur = conn.execute(
            """
            UPDATE factor_dashboard_metrics
            SET ic_mean=NULL, ic_std=NULL, ir=NULL, rank_ic=NULL,
                q1_return=NULL, q5_return=NULL, long_short_spread=NULL,
                q1_turnover=NULL, q5_turnover=NULL,
                coverage_pool=NULL, coverage_total=NULL,
                win_rate=NULL, volatility=NULL,
                sharpe=NULL, annual_return=NULL, max_drawdown=NULL,
                error=?, computed_at=?
            WHERE factor_name=? AND rules_version=?
            """,
            (reason[:500], now, name, RULES_VERSION),
        )
        print(f"  {name}: cleared {cur.rowcount} rows -> {reason}")
        total += cur.rowcount
    conn.commit()
    conn.close()
    print(f"done total_rows={total}")


if __name__ == "__main__":
    main()
