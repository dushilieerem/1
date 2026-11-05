# -*- coding: utf-8 -*-
"""机构端单维 AI 对话持久化。"""
from __future__ import annotations

from typing import Any

from services.core.db import get_conn


def member_user_id(org_id: int, member_id: int | None) -> int | None:
    if not member_id:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id FROM inst_members WHERE id=%s AND org_id=%s",
            (member_id, org_id),
        ).fetchone()
    return int(row["user_id"]) if row and row["user_id"] else None


def list_messages(
    org_id: int,
    case_id: int,
    dim_key: str,
    user_id: int,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at
              FROM inst_ai_chat_message
             WHERE org_id=%s AND case_id=%s AND dim_key=%s AND user_id=%s
             ORDER BY id DESC LIMIT %s
            """,
            (org_id, case_id, dim_key, user_id, max(1, min(int(limit), 200))),
        ).fetchall()
    return [
        {
            "role": str(r["role"]),
            "content": str(r["content"]),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in reversed(rows)
    ]


def append_message(
    org_id: int,
    case_id: int,
    dim_key: str,
    user_id: int,
    *,
    member_id: int | None,
    role: str,
    content: str,
    client_message_id: str | None = None,
) -> None:
    if role not in {"user", "assistant"}:
        raise ValueError("role 必须是 user/assistant")
    text = str(content or "").strip()
    if not text:
        return
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO inst_ai_chat_message
              (org_id, case_id, dim_key, user_id, member_id, role, content, client_message_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (org_id, case_id, dim_key, user_id, member_id, role, text[:8000], client_message_id),
        )
