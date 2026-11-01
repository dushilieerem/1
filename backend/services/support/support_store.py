# -*- coding: utf-8 -*-
"""客服工单（H14）：用户提交、双向回复、管理员关闭。"""
from __future__ import annotations

from typing import Any

from services.core.db import get_conn

CATEGORIES = {"account", "data", "ai", "community", "billing", "other"}
STATUSES = {"open", "in_progress", "closed"}


def ensure_support_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
              id          BIGSERIAL PRIMARY KEY,
              user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              category    TEXT NOT NULL DEFAULT 'other',
              subject     TEXT NOT NULL,
              body        TEXT NOT NULL,
              status      TEXT NOT NULL DEFAULT 'open',
              priority    TEXT NOT NULL DEFAULT 'normal',
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS support_ticket_replies (
              id          BIGSERIAL PRIMARY KEY,
              ticket_id   BIGINT NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
              author_type TEXT NOT NULL,
              author_id   BIGINT,
              body        TEXT NOT NULL,
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_support_tickets_user ON support_tickets (user_id, updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets (status, updated_at DESC)"
        )


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("created_at", "updated_at"):
        out[key] = _iso(out.get(key))
    return out


def create_ticket(user_id: int, *, category: str, subject: str, body: str) -> dict[str, Any]:
    ensure_support_schema()
    cat = (category or "other").strip().lower()
    if cat not in CATEGORIES:
        raise ValueError("分类不合法")
    title = (subject or "").strip()
    if not (2 <= len(title) <= 120):
        raise ValueError("标题需 2–120 字")
    text = (body or "").strip()
    if not (1 <= len(text) <= 5000):
        raise ValueError("内容需 1–5000 字")
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO support_tickets (user_id, category, subject, body) "
            "VALUES (%s,%s,%s,%s) RETURNING *",
            (int(user_id), cat, title, text),
        ).fetchone()
    return _row(dict(row))


def list_my_tickets(user_id: int, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    ensure_support_schema()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM support_tickets WHERE user_id=%s ORDER BY updated_at DESC LIMIT %s OFFSET %s",
            (int(user_id), max(1, min(limit, 100)), max(0, offset)),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM support_tickets WHERE user_id=%s", (int(user_id),)
        ).fetchone()["n"]
    return {"items": [_row(dict(r)) for r in rows], "total": int(total or 0)}


def _ticket(conn, ticket_id: int, *, user_id: int | None = None) -> dict[str, Any] | None:
    sql = "SELECT * FROM support_tickets WHERE id=%s"
    params: list[Any] = [ticket_id]
    if user_id is not None:
        sql += " AND user_id=%s"
        params.append(user_id)
    row = conn.execute(sql, tuple(params)).fetchone()
    if not row:
        return None
    out = _row(dict(row))
    replies = conn.execute(
        "SELECT * FROM support_ticket_replies WHERE ticket_id=%s ORDER BY created_at",
        (ticket_id,),
    ).fetchall()
    out["replies"] = [
        {**_row(dict(r)), "author_id": int(r["author_id"]) if r.get("author_id") else None}
        for r in replies
    ]
    return out


def get_my_ticket(user_id: int, ticket_id: int) -> dict[str, Any]:
    ensure_support_schema()
    with get_conn() as conn:
        out = _ticket(conn, ticket_id, user_id=int(user_id))
    if not out:
        raise KeyError(ticket_id)
    return out


def add_user_reply(user_id: int, ticket_id: int, body: str) -> dict[str, Any]:
    text = (body or "").strip()
    if not (1 <= len(text) <= 5000):
        raise ValueError("回复需 1–5000 字")
    ensure_support_schema()
    with get_conn() as conn:
        ticket = conn.execute(
            "SELECT status FROM support_tickets WHERE id=%s AND user_id=%s",
            (ticket_id, user_id),
        ).fetchone()
        if not ticket:
            raise KeyError(ticket_id)
        if ticket["status"] == "closed":
            raise ValueError("工单已关闭，不能继续回复")
        conn.execute(
            "INSERT INTO support_ticket_replies (ticket_id, author_type, author_id, body) "
            "VALUES (%s,'user',%s,%s)",
            (ticket_id, int(user_id), text),
        )
        conn.execute(
            "UPDATE support_tickets SET status='open', updated_at=NOW() WHERE id=%s", (ticket_id,)
        )
    return get_my_ticket(user_id, ticket_id)


def admin_list_tickets(
    *, status: str | None = None, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    ensure_support_schema()
    if status and status not in STATUSES:
        raise ValueError("status 不合法")
    with get_conn() as conn:
        sql = (
            "SELECT t.*, u.username FROM support_tickets t "
            "JOIN users u ON u.id=t.user_id"
        )
        params: list[Any] = []
        if status:
            sql += " WHERE t.status=%s"
            params.append(status)
        sql += " ORDER BY t.updated_at DESC LIMIT %s OFFSET %s"
        params += [max(1, min(limit, 200)), max(0, offset)]
        rows = conn.execute(sql, tuple(params)).fetchall()
        total_sql = "SELECT COUNT(*) AS n FROM support_tickets t"
        if status:
            total_sql += " WHERE t.status=%s"
        total = conn.execute(total_sql, tuple([status] if status else [])).fetchone()["n"]
    return {"items": [_row(dict(r)) for r in rows], "total": int(total or 0)}


def admin_get_ticket(ticket_id: int) -> dict[str, Any]:
    ensure_support_schema()
    with get_conn() as conn:
        out = _ticket(conn, ticket_id)
    if not out:
        raise KeyError(ticket_id)
    return out


def admin_reply(
    admin_id: int,
    ticket_id: int,
    body: str,
    *,
    status: str | None = None,
) -> dict[str, Any]:
    text = (body or "").strip()
    if not (1 <= len(text) <= 5000):
        raise ValueError("回复需 1–5000 字")
    if status is not None and status not in STATUSES:
        raise ValueError("status 不合法")
    ensure_support_schema()
    with get_conn() as conn:
        ticket = conn.execute("SELECT id FROM support_tickets WHERE id=%s", (ticket_id,)).fetchone()
        if not ticket:
            raise KeyError(ticket_id)
        conn.execute(
            "INSERT INTO support_ticket_replies (ticket_id, author_type, author_id, body) "
            "VALUES (%s,'admin',%s,%s)",
            (ticket_id, int(admin_id), text),
        )
        next_status = status or "in_progress"
        conn.execute(
            "UPDATE support_tickets SET status=%s, updated_at=NOW() WHERE id=%s",
            (next_status, ticket_id),
        )
    return admin_get_ticket(ticket_id)
