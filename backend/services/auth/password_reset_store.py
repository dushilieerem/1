# -*- coding: utf-8 -*-
"""主站找回密码：一次性 token（30 分钟有效）。

当前环境未接 SMTP：接口默认只返回通用提示；开发/内测设
`AUTH_RESET_DEBUG=1` 时把 token 返回给调用方，便于联调。
生产接入邮件服务后，把 token 放进重置链接即可。
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from services.auth.auth_store import hash_password
from services.core.db import get_conn

TOKEN_TTL_MINUTES = 30


def ensure_password_reset_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
              id BIGSERIAL PRIMARY KEY,
              user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              token_hash TEXT NOT NULL UNIQUE,
              expires_at TIMESTAMPTZ NOT NULL,
              used_at TIMESTAMPTZ,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens (user_id, created_at DESC)")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_reset(identifier: str) -> str | None:
    ident = (identifier or "").strip()
    if not ident:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE (username=%s OR email=%s) AND status='active' LIMIT 1",
            (ident, ident),
        ).fetchone()
        if not row:
            return None
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (%s,%s,%s)",
            (int(row["id"]), _hash(token), datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)),
        )
        return token


def reset_password(token: str, password: str) -> None:
    if len(password or "") < 6:
        raise ValueError("密码至少 6 位")
    if not token:
        raise ValueError("缺少重置 token")
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, user_id FROM password_reset_tokens
             WHERE token_hash=%s AND used_at IS NULL AND expires_at > NOW()
             LIMIT 1
            """,
            (_hash(token),),
        ).fetchone()
        if not row:
            raise ValueError("重置 token 无效或已过期")
        conn.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hash_password(password), int(row["user_id"])))
        conn.execute("UPDATE password_reset_tokens SET used_at=NOW() WHERE id=%s", (int(row["id"]),))


__all__ = ["ensure_password_reset_schema", "request_reset", "reset_password"]
