# -*- coding: utf-8 -*-
"""多步研究 Agent 运行状态（P1-A02）。

目标 → 搜集 → 假设 → 因子 → 回测 → 评价 → 报告。
每一步的输出由调用方（前端/Agent）提交，服务端只维护状态与人工确认节点，
因此可随时中断、换设备后继续。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from services.core.db import get_conn

STEPS = ("gather", "idea", "factor", "backtest", "eval", "report")
# 进入下一步前需要人工确认
CONFIRM_STEPS = {"backtest", "report"}
_TERMINAL = {"completed", "cancelled", "failed"}


def ensure_research_run_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_research_runs (
              id           BIGSERIAL PRIMARY KEY,
              user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              goal         TEXT NOT NULL,
              status       TEXT NOT NULL DEFAULT 'running',
              current_step TEXT NOT NULL DEFAULT 'gather',
              context      JSONB NOT NULL DEFAULT '{}'::jsonb,
              created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_research_runs_user "
            "ON ai_research_runs (user_id, updated_at DESC)"
        )


def _row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["created_at"] = row["created_at"].isoformat()
    item["updated_at"] = row["updated_at"].isoformat()
    item["context"] = row.get("context") or {}
    return item


def create_run(user_id: int, goal: str) -> dict[str, Any]:
    ensure_research_run_schema()
    text = (goal or "").strip()
    if not text:
        raise ValueError("研究目标不能为空")
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO ai_research_runs (user_id, goal) VALUES (%s, %s) RETURNING *",
            (int(user_id), text[:500]),
        ).fetchone()
    return _row(dict(row))


def get_run(user_id: int, run_id: int) -> dict[str, Any] | None:
    ensure_research_run_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM ai_research_runs WHERE id = %s AND user_id = %s",
            (int(run_id), int(user_id)),
        ).fetchone()
    return _row(dict(row)) if row else None


def list_runs(user_id: int, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    ensure_research_run_schema()
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM ai_research_runs WHERE user_id = %s",
            (int(user_id),),
        ).fetchone()
        rows = conn.execute(
            "SELECT * FROM ai_research_runs WHERE user_id = %s "
            "ORDER BY updated_at DESC, id DESC LIMIT %s OFFSET %s",
            (int(user_id), limit, offset),
        ).fetchall()
    return {
        "ok": True,
        "items": [_row(dict(r)) for r in rows],
        "total": int(total["n"] or 0),
        "limit": limit,
        "offset": offset,
    }


def transition(
    *, current_step: str, step: str, approve: bool, fail: str | None, status: str
) -> tuple[str, str]:
    """纯状态机：返回 (status, current_step)。"""
    if step not in STEPS:
        raise ValueError(f"未知步骤: {step}")
    if current_step != step:
        raise ValueError(f"当前步骤是 {current_step}，不能提交 {step}")
    if fail:
        return "failed", current_step
    if step in CONFIRM_STEPS and not approve:
        return "waiting_confirmation", current_step
    idx = STEPS.index(step)
    if idx + 1 >= len(STEPS):
        return "completed", current_step
    return "running", STEPS[idx + 1]


def advance_run(
    user_id: int,
    run_id: int,
    *,
    step: str,
    output: Any = None,
    approve: bool = False,
    fail: str | None = None,
) -> dict[str, Any] | None:
    """提交某一步输出并推进；人工确认步骤未 approve 时保持原状。"""
    if step not in STEPS:
        raise ValueError(f"未知步骤: {step}")
    run = get_run(user_id, run_id)
    if run is None:
        return None
    if run["status"] in _TERMINAL:
        raise ValueError(f"运行已结束（{run['status']}）")
    if run["current_step"] != step:
        raise ValueError(f"当前步骤是 {run['current_step']}，不能提交 {step}")

    context = dict(run.get("context") or {})
    context[step] = {"output": output, "finished_at": datetime.now(timezone.utc).isoformat()}
    if fail:
        context["error"] = str(fail)[:500]
    status, current = transition(
        current_step=run["current_step"],
        step=step,
        approve=approve,
        fail=fail,
        status=run["status"],
    )

    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE ai_research_runs
            SET status = %s, current_step = %s, context = %s::jsonb, updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (
                status,
                current,
                json.dumps(context, ensure_ascii=False, default=str),
                int(run_id),
                int(user_id),
            ),
        ).fetchone()
    return _row(dict(row)) if row else None


def cancel_run(user_id: int, run_id: int) -> dict[str, Any] | None:
    ensure_research_run_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE ai_research_runs SET status = 'cancelled', updated_at = NOW()
            WHERE id = %s AND user_id = %s RETURNING *
            """,
            (int(run_id), int(user_id)),
        ).fetchone()
    return _row(dict(row)) if row else None
