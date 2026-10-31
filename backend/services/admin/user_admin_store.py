# -*- coding: utf-8 -*-
"""主站管理员：用户查询与账号治理。

- 只操作 `users` 表；不下沉业务权限。
- 不能禁用/降级最后一个有效管理员。
"""
from __future__ import annotations

from typing import Any

from services.auth.auth_store import hash_password
from services.core.db import get_conn

USER_COLUMNS = "id, username, email, role, status, display_name, created_at"


def _public(row: Any) -> dict[str, Any]:
    out = dict(row)
    if out.get("created_at") is not None:
        out["created_at"] = out["created_at"].isoformat()
    return out


def list_users(
    *,
    q: str | None = None,
    status: str | None = None,
    role: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    where: list[str] = []
    params: list[Any] = []
    if q:
        where.append("(username ILIKE %s OR email ILIKE %s OR display_name ILIKE %s)")
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    if status:
        where.append("status=%s")
        params.append(status)
    if role:
        where.append("role=%s")
        params.append(role)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total = int(conn.execute(f"SELECT COUNT(*) AS n FROM users{clause}", tuple(params)).fetchone()["n"] or 0)
        rows = conn.execute(
            f"SELECT {USER_COLUMNS} FROM users{clause} ORDER BY id DESC LIMIT %s OFFSET %s",
            tuple(params + [limit, offset]),
        ).fetchall()
    return {"items": [_public(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def _active_admin_count(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND status='active'").fetchone()
    return int(row["n"] or 0)


def _target(conn, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id=%s", (user_id,)).fetchone()
    return _public(row) if row else None


def set_status(user_id: int, status: str) -> dict[str, Any]:
    if status not in {"active", "disabled"}:
        raise ValueError("status 必须是 active/disabled")
    with get_conn() as conn:
        target = _target(conn, user_id)
        if not target:
            raise LookupError("用户不存在")
        if target["role"] == "admin" and target["status"] == "active" and status != "active":
            if _active_admin_count(conn) <= 1:
                raise ValueError("不能禁用最后一个有效管理员")
        conn.execute("UPDATE users SET status=%s WHERE id=%s", (status, user_id))
        return _target(conn, user_id) or {}


def set_role(user_id: int, role: str) -> dict[str, Any]:
    if role not in {"user", "admin"}:
        raise ValueError("role 必须是 user/admin")
    with get_conn() as conn:
        target = _target(conn, user_id)
        if not target:
            raise LookupError("用户不存在")
        if target["role"] == "admin" and role != "admin" and target["status"] == "active":
            if _active_admin_count(conn) <= 1:
                raise ValueError("不能降级最后一个有效管理员")
        conn.execute("UPDATE users SET role=%s WHERE id=%s", (role, user_id))
        return _target(conn, user_id) or {}


def reset_password(user_id: int, password: str) -> dict[str, Any]:
    if len(password or "") < 6:
        raise ValueError("密码至少 6 位")
    with get_conn() as conn:
        target = _target(conn, user_id)
        if not target:
            raise LookupError("用户不存在")
        conn.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hash_password(password), user_id))
        return {"id": user_id, "username": target["username"]}


__all__ = ["list_users", "reset_password", "set_role", "set_status"]
