# -*- coding: utf-8 -*-
"""Agent 用量记账 + 日配额（对照 users.ai_quota_daily）。"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from services.core.db import get_conn


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


def usage_summary_for_user(user_id: int, *, days: int = 7) -> dict[str, Any]:
    """用户自己的用量：今日配额 + 近 N 日 totals / by_day / by_skill。"""
    ensure_ai_usage_schema()
    days = max(1, min(90, int(days)))
    q = get_user_quota(user_id)
    with get_conn() as conn:
        by_skill_today = conn.execute(
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
        totals = conn.execute(
            """
            SELECT COUNT(*)::int AS calls,
                   COUNT(DISTINCT run_id)::int AS runs,
                   COALESCE(SUM(tokens_in), 0)::int AS tokens_in,
                   COALESCE(SUM(tokens_out), 0)::int AS tokens_out
            FROM ai_usage
            WHERE user_id = %s
              AND created_at >= NOW() - (%s * INTERVAL '1 day')
            """,
            (user_id, days),
        ).fetchone()
        by_day_rows = conn.execute(
            """
            SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
                   COUNT(*)::int AS calls,
                   COALESCE(SUM(tokens_in), 0)::int AS tokens_in,
                   COALESCE(SUM(tokens_out), 0)::int AS tokens_out
            FROM ai_usage
            WHERE user_id = %s
              AND created_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY date_trunc('day', created_at)
            ORDER BY day ASC
            """,
            (user_id, days),
        ).fetchall()
        by_skill = conn.execute(
            """
            SELECT skill, COUNT(*)::int AS calls,
                   COALESCE(SUM(tokens_in), 0)::int AS tokens_in,
                   COALESCE(SUM(tokens_out), 0)::int AS tokens_out
            FROM ai_usage
            WHERE user_id = %s
              AND created_at >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY skill
            ORDER BY calls DESC
            """,
            (user_id, days),
        ).fetchall()

    # 补齐近 N 个自然日（无调用填 0），便于前端画趋势
    from datetime import timedelta

    today = date.today()
    by_day_map = {str(r["day"]): dict(r) for r in by_day_rows}
    by_day: list[dict[str, Any]] = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        hit = by_day_map.get(d)
        if hit:
            by_day.append(
                {
                    "day": d,
                    "calls": int(hit["calls"]),
                    "tokens_in": int(hit["tokens_in"]),
                    "tokens_out": int(hit["tokens_out"]),
                }
            )
        else:
            by_day.append({"day": d, "calls": 0, "tokens_in": 0, "tokens_out": 0})

    t = dict(totals) if totals else {
        "calls": 0,
        "runs": 0,
        "tokens_in": 0,
        "tokens_out": 0,
    }
    return {
        **q,
        "days": days,
        "totals": {
            "calls": int(t.get("calls") or 0),
            "runs": int(t.get("runs") or 0),
            "tokens_in": int(t.get("tokens_in") or 0),
            "tokens_out": int(t.get("tokens_out") or 0),
        },
        "by_day": by_day,
        "by_skill": [dict(r) for r in by_skill],
        "by_skill_today": [dict(r) for r in by_skill_today],
    }


def usage_admin_summary(*, days: int = 7, limit: int = 200) -> dict[str, Any]:
    """管理员：全站汇总 + 各用户（含日上限 / 今日已用 / 近 N 日调用）。"""
    ensure_ai_usage_schema()
    days = max(1, min(90, int(days)))
    limit = max(1, min(500, int(limit)))
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
            SELECT
              u.id AS user_id,
              u.username,
              u.display_name,
              u.role,
              COALESCE(u.ai_quota_daily, 200)::int AS quota_daily,
              COALESCE(today.c, 0)::int AS used_today,
              COALESCE(period.calls, 0)::int AS calls,
              COALESCE(period.tokens_in, 0)::int AS tokens_in,
              COALESCE(period.tokens_out, 0)::int AS tokens_out
            FROM users u
            LEFT JOIN (
              SELECT user_id, COUNT(*)::int AS c
              FROM ai_usage
              WHERE created_at >= date_trunc('day', NOW())
              GROUP BY user_id
            ) today ON today.user_id = u.id
            LEFT JOIN (
              SELECT user_id,
                     COUNT(*)::int AS calls,
                     COALESCE(SUM(tokens_in), 0)::int AS tokens_in,
                     COALESCE(SUM(tokens_out), 0)::int AS tokens_out
              FROM ai_usage
              WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
              GROUP BY user_id
            ) period ON period.user_id = u.id
            WHERE u.status = 'active'
            ORDER BY COALESCE(period.calls, 0) DESC, u.id ASC
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
    users = []
    for r in by_user:
        d = dict(r)
        quota = int(d.get("quota_daily") or 0)
        used = int(d.get("used_today") or 0)
        d["remaining"] = max(0, quota - used)
        users.append(d)
    return {
        "days": days,
        "totals": dict(totals)
        if totals
        else {"calls": 0, "tokens_in": 0, "tokens_out": 0, "users": 0},
        "by_user": users,
        "by_skill": [dict(r) for r in by_skill],
    }


def set_user_ai_quota(
    *,
    author_role: str,
    user_id: int,
    quota_daily: int,
) -> dict[str, Any]:
    """管理员修改用户日配额（调用次数上限）。"""
    if author_role != "admin":
        raise PermissionError("仅管理员可修改配额")
    q = int(quota_daily)
    if q < 0 or q > 100000:
        raise ValueError("日配额须在 0～100000")
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE users
            SET ai_quota_daily = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, username, display_name, ai_quota_daily
            """,
            (q, int(user_id)),
        ).fetchone()
        if not row:
            raise KeyError(f"user not found: {user_id}")
        used = conn.execute(
            """
            SELECT COUNT(*)::int AS c
            FROM ai_usage
            WHERE user_id = %s
              AND created_at >= date_trunc('day', NOW())
            """,
            (int(user_id),),
        ).fetchone()["c"]
    quota = int(row["ai_quota_daily"])
    return {
        "ok": True,
        "user": {
            "user_id": int(row["id"]),
            "username": row["username"],
            "display_name": row.get("display_name") or row["username"],
            "quota_daily": quota,
            "used_today": int(used),
            "remaining": max(0, quota - int(used)),
        },
    }
