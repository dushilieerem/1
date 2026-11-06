"""M4 read-only monitoring overview built from real research/portfolio records."""
from __future__ import annotations

from services.core.db import get_conn


def overview(uid: int, org: int):
    events = []
    with get_conn() as c:
        factor_errors = c.execute(
            """SELECT id,project_id,snapshot->>'name' AS name,status,updated_at,events
               FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND status LIKE '%%_error'
               ORDER BY updated_at DESC LIMIT 50""", (uid, org)).fetchall()
        f0 = c.execute(
            """SELECT id,topic_id,status,stop_reason,updated_at FROM quant_factor_f0_runs
               WHERE user_id=%s AND org_id=%s AND status IN ('stopped','failed','error')
               ORDER BY updated_at DESC LIMIT 50""", (uid, org)).fetchall()
        s0 = c.execute(
            """SELECT id,topic_id,status,stop_reason,updated_at FROM strategy_s0_runs
               WHERE user_id=%s AND org_id=%s AND status IN ('failed','stopped')
               ORDER BY updated_at DESC LIMIT 50""", (uid, org)).fetchall()
        plans = c.execute(
            """SELECT id,name,status,updated_at FROM portfolio_plans WHERE user_id=%s AND org_id=%s
               AND status IN ('submitted','approved','stopped') ORDER BY updated_at DESC LIMIT 50""", (uid, org)).fetchall()
        counts = c.execute(
            """SELECT
                 (SELECT COUNT(*) FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND status LIKE '%%_running') AS running,
                 (SELECT COUNT(*) FROM quant_factor_candidates WHERE user_id=%s AND org_id=%s AND status LIKE '%%_error') AS errors,
                 (SELECT COUNT(*) FROM strategy_trials WHERE user_id=%s AND org_id=%s AND created_at > NOW()-INTERVAL '30 days') AS strategy_trials_30d,
                 (SELECT COUNT(*) FROM quant_factor_trials WHERE user_id=%s AND org_id=%s AND created_at > NOW()-INTERVAL '30 days') AS factor_trials_30d""",
            (uid, org, uid, org, uid, org, uid, org)).fetchone()
    for row in factor_errors:
        events.append({"severity": "warning", "kind": "factor_calculation", "object": row["name"] or row["id"][:8],
                       "detail": row["status"], "at": row["updated_at"].isoformat(), "ref": row["id"]})
    for row in f0:
        reason = row["stop_reason"] or ""
        events.append({"severity": "warning" if "中断" not in reason else "serious", "kind": "factor_f0",
                       "object": "F0 " + row["topic_id"][:8], "detail": reason[:200],
                       "at": row["updated_at"].isoformat(), "ref": row["id"]})
    for row in s0:
        events.append({"severity": "warning", "kind": "strategy_s0", "object": "S0 " + row["topic_id"][:8],
                       "detail": (row["stop_reason"] or row["status"])[:200],
                       "at": row["updated_at"].isoformat(), "ref": row["id"]})
    for row in plans:
        events.append({"severity": "info" if row["status"] != "stopped" else "warning", "kind": "portfolio",
                       "object": row["name"], "detail": row["status"], "at": row["updated_at"].isoformat(),
                       "ref": row["id"]})
    events.sort(key=lambda x: x["at"], reverse=True)
    return {"counts": dict(counts), "events": events[:100],
            "limitations": [
                "巡检为按需读取真实记录，尚未接入常驻定时任务（RK-M1 待接入）。",
                "严重事件自动暂停模拟组合、恢复复测证据尚未接入。",
                "归因与改进任务尚未接入。",
            ]}


__all__ = ["overview"]
