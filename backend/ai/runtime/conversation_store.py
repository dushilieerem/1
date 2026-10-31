# -*- coding: utf-8 -*-
"""AI 会话与研究历史（P1-A01）：服务端会话 + 消息，跨设备可查/可删。

浏览器仍可缓存，但以服务端为准；保留策略由 AI_CONVERSATION_RETENTION_DAYS 控制。
"""
from __future__ import annotations

from typing import Any

from services.core.db import get_conn


def ensure_conversation_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_conversations (
              id         BIGSERIAL PRIMARY KEY,
              user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              title      TEXT NOT NULL DEFAULT '新会话',
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_conversations_user "
            "ON ai_conversations (user_id, updated_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_messages (
              id              BIGSERIAL PRIMARY KEY,
              conversation_id BIGINT NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
              role            TEXT NOT NULL,
              content         TEXT NOT NULL,
              model           TEXT,
              tokens_in       INT NOT NULL DEFAULT 0,
              tokens_out      INT NOT NULL DEFAULT 0,
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation "
            "ON ai_messages (conversation_id, id)"
        )


def _title(text: str) -> str:
    raw = " ".join((text or "").split())
    return (raw[:60] or "新会话") if raw else "新会话"


def create_conversation(user_id: int, *, title: str = "", first_message: str = "") -> dict[str, Any]:
    ensure_conversation_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO ai_conversations (user_id, title)
            VALUES (%s, %s)
            RETURNING id, title, created_at, updated_at
            """,
            (int(user_id), _title(title or first_message)),
        ).fetchone()
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def list_conversations(user_id: int, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    ensure_conversation_schema()
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM ai_conversations WHERE user_id = %s",
            (int(user_id),),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM ai_messages m WHERE m.conversation_id = c.id) AS message_count
            FROM ai_conversations c
            WHERE c.user_id = %s
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT %s OFFSET %s
            """,
            (int(user_id), limit, offset),
        ).fetchall()
    items = []
    for r in rows:
        item = dict(r)
        item["created_at"] = r["created_at"].isoformat()
        item["updated_at"] = r["updated_at"].isoformat()
        item["message_count"] = int(r["message_count"] or 0)
        items.append(item)
    return {"ok": True, "items": items, "total": int(total["n"] or 0), "limit": limit, "offset": offset}


def get_conversation(user_id: int, conversation_id: int) -> dict[str, Any] | None:
    ensure_conversation_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM ai_conversations "
            "WHERE id = %s AND user_id = %s",
            (int(conversation_id), int(user_id)),
        ).fetchone()
        if not row:
            return None
        msgs = conn.execute(
            """
            SELECT id, role, content, model, tokens_in, tokens_out, created_at
            FROM ai_messages WHERE conversation_id = %s ORDER BY id
            """,
            (int(conversation_id),),
        ).fetchall()
    items = []
    for m in msgs:
        item = dict(m)
        item["created_at"] = m["created_at"].isoformat()
        items.append(item)
    return {
        "ok": True,
        "id": int(row["id"]),
        "title": row["title"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "messages": items,
    }


def append_message(
    user_id: int,
    conversation_id: int,
    *,
    role: str,
    content: str,
    model: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> int | None:
    """追加消息；会话不属于该用户时返回 None（不泄露存在性）。"""
    ensure_conversation_schema()
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM ai_conversations WHERE id = %s AND user_id = %s",
            (int(conversation_id), int(user_id)),
        ).fetchone()
        if not exists:
            return None
        row = conn.execute(
            """
            INSERT INTO ai_messages
              (conversation_id, role, content, model, tokens_in, tokens_out)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                int(conversation_id),
                str(role),
                str(content or ""),
                model,
                int(tokens_in or 0),
                int(tokens_out or 0),
            ),
        ).fetchone()
        conn.execute(
            "UPDATE ai_conversations SET updated_at = NOW() WHERE id = %s",
            (int(conversation_id),),
        )
    return int(row["id"])


def delete_conversation(user_id: int, conversation_id: int) -> bool:
    ensure_conversation_schema()
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM ai_conversations WHERE id = %s AND user_id = %s",
            (int(conversation_id), int(user_id)),
        )
        return cur.rowcount > 0


def purge_old_conversations(days: int | None = None) -> int:
    """保留策略清理；days<=0 不清理。"""
    from services.core.env_config import env

    if days is None:
        try:
            days = int(env("AI_CONVERSATION_RETENTION_DAYS", "90") or "90")
        except (TypeError, ValueError):
            days = 90
    if days <= 0:
        return 0
    ensure_conversation_schema()
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM ai_conversations "
            "WHERE updated_at < NOW() - make_interval(days => %s)",
            (int(days),),
        )
        return int(cur.rowcount or 0)
