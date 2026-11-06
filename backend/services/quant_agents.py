"""M5 Agent management read-only overview (usage per capability unit)."""
from __future__ import annotations

from services.core.db import get_conn

LABELS = {
    "quant.factor.f0_decider": ("F0", "研究决策 Agent"),
    "quant.strategy.s0_decider": ("S0", "策略研究决策"),
    "research.generate_factor": ("F3", "因子生成与校验"),
    "qf-plan-suggest": ("F2", "研究计划助手"),
    "qf-plan-v2": ("F2", "研究计划助手"),
}


def overview(uid: int, org: int):
    with get_conn() as c:
        rows = [dict(r) for r in c.execute(
            """SELECT u.skill, COUNT(*)::int AS calls,
                      COALESCE(SUM(u.tokens_in),0)::int AS tokens_in,
                      COALESCE(SUM(u.tokens_out),0)::int AS tokens_out,
                      MAX(u.created_at) AS last_at
               FROM ai_usage u
               JOIN inst_members m ON m.user_id=u.user_id AND m.org_id=%s
               WHERE u.created_at >= NOW() - INTERVAL '30 days'
               GROUP BY u.skill ORDER BY calls DESC""", (org,)).fetchall()]
    units = []
    for r in rows:
        code, name = LABELS.get(r["skill"], ("AI", r["skill"]))
        units.append({"code": code, "name": name, "skill": r["skill"], "calls": r["calls"],
                      "tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"],
                      "last_at": r["last_at"].isoformat() if r["last_at"] else None,
                      "method_version": "prompt version 记录在调用中", "failure_rate": None})
    return {"window_days": 30, "units": units,
            "limitations": ["失败率未按 skill 记录，显示待接入。",
                            "Agent 暂停接口尚未接入；暂停后自动推进停止需新增控制表与 worker 检查。"]}
