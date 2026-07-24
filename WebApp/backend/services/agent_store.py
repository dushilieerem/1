# -*- coding: utf-8 -*-
"""Agent 用量记账 + 日配额（对照 users.ai_quota_daily）。"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from services.db import get_conn


def ensure_ai_usage_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
              id           BIGSERIAL PRIMARY KEY,
              user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              run_id       TEXT NOT NULL,
              skill        TEXT NOT NULL,
              tokens_in    INTEGER NOT NULL DEFAULT 0,
              tokens_out   INTEGER NOT NULL DEFAULT 0,
              created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_usage_user_day ON ai_usage (user_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_usage_run ON ai_usage (run_id)"
        )


def new_run_id() -> str:
    return uuid.uuid4().hex


def usage_today_count(user_id: int) -> int:
    ensure_ai_usage_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)::int AS c
            FROM ai_usage
            WHERE user_id = %s
              AND created_at >= date_trunc('day', NOW())
            """,
            (user_id,),
        ).fetchone()
    return int(row["c"] if row else 0)


def get_user_quota(user_id: int) -> dict[str, Any]:
    ensure_ai_usage_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT ai_quota_daily FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    if not row:
        raise LookupError("用户不存在")
    quota = int(row["ai_quota_daily"] or 0)
    used = usage_today_count(user_id)
    return {
        "quota_daily": quota,
        "used_today": used,
        "remaining": max(0, quota - used),
        "day": date.today().isoformat(),
    }


def assert_quota_available(user_id: int, need: int = 1) -> dict[str, Any]:
    info = get_user_quota(user_id)
    if info["remaining"] < need:
        raise PermissionError(
            f"今日 AI 配额已用尽（{info['used_today']}/{info['quota_daily']}）"
        )
    return info


def record_usage(
    *,
    user_id: int,
    run_id: str,
    skill: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    ensure_ai_usage_schema()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ai_usage (user_id, run_id, skill, tokens_in, tokens_out)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, run_id, skill, int(tokens_in or 0), int(tokens_out or 0)),
        )


def usage_summary_for_user(user_id: int) -> dict[str, Any]:
    q = get_user_quota(user_id)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT skill, COUNT(*)::int AS calls,
                   COALESCE(SUM(tokens_in), 0)::int AS tokens_in,
                   COALESCE(SUM(tokens_out), 0)::int AS tokens_out
            FROM ai_usage
            WHERE user_id = %s
              AND created_at >= date_trunc('day', NOW())
            GROUP BY skill
            ORDER BY calls DESC
            """,
            (user_id,),
        ).fetchall()
    return {
        **q,
        "by_skill": [dict(r) for r in rows],
    }


def usage_admin_summary(*, days: int = 7, limit: int = 50) -> dict[str, Any]:
    ensure_ai_usage_schema()
    days = max(1, min(90, int(days)))
    limit = max(1, min(200, int(limit)))
    with get_conn() as conn:
        totals = conn.execute(
            """
            SELECT COUNT(*)::int AS calls,
                   COALESCE(SUM(tokens_in), 0)::int AS tokens_in,
                   COALESCE(SUM(tokens_out), 0)::int AS tokens_out,
                   COUNT(DISTINCT user_id)::int AS users
            FROM ai_usage
            WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
            """,
            (days,),
        ).fetchone()
        by_user = conn.execute(
            """
            SELECT u.id AS user_id, u.username,
                   COUNT(*)::int AS calls,
                   COALESCE(SUM(a.tokens_in), 0)::int AS tokens_in,
                   COALESCE(SUM(a.tokens_out), 0)::int AS tokens_out
            FROM ai_usage a
            JOIN users u ON u.id = a.user_id
            WHERE a.created_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY u.id, u.username
            ORDER BY calls DESC
            LIMIT %s
            """,
            (days, limit),
        ).fetchall()
        by_skill = conn.execute(
            """
            SELECT skill, COUNT(*)::int AS calls,
                   COALESCE(SUM(tokens_in), 0)::int AS tokens_in,
                   COALESCE(SUM(tokens_out), 0)::int AS tokens_out
            FROM ai_usage
            WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY skill
            ORDER BY calls DESC
            """,
            (days,),
        ).fetchall()
    return {
        "days": days,
        "totals": dict(totals) if totals else {"calls": 0, "tokens_in": 0, "tokens_out": 0, "users": 0},
        "by_user": [dict(r) for r in by_user],
        "by_skill": [dict(r) for r in by_skill],
    }
