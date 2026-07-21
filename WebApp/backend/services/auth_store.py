# -*- coding: utf-8 -*-
"""用户表 + 注册/登录（JWT）。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from services.db import get_conn
from services.env_config import env

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def _jwt_secret() -> str:
    return env("JWT_SECRET", "svquant-dev-jwt-secret-change-me") or "svquant-dev-jwt-secret-change-me"


def _jwt_expire_days() -> int:
    try:
        return max(1, int(env("JWT_EXPIRE_DAYS", "7") or "7"))
    except ValueError:
        return 7


def dev_skip_auth() -> bool:
    return (env("DEV_SKIP_AUTH", "0") or "0").strip() in {"1", "true", "True", "yes"}


def ensure_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id              BIGSERIAL PRIMARY KEY,
              username        TEXT NOT NULL UNIQUE,
              email           TEXT UNIQUE,
              password_hash   TEXT NOT NULL,
              role            TEXT NOT NULL DEFAULT 'user',
              status          TEXT NOT NULL DEFAULT 'active',
              display_name    TEXT,
              ai_quota_daily  INTEGER NOT NULL DEFAULT 50,
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT users_role_chk CHECK (role IN ('user', 'admin')),
              CONSTRAINT users_status_chk CHECK (status IN ('active', 'disabled'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_status ON users (status)"
        )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row.get("email"),
        "role": row["role"],
        "status": row["status"],
        "display_name": row.get("display_name") or row["username"],
        "ai_quota_daily": row.get("ai_quota_daily", 50),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = %s",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def seed_admin() -> dict[str, Any]:
    ensure_schema()
    username = (env("ADMIN_USERNAME", "admin") or "admin").strip()
    password = env("ADMIN_PASSWORD", "admin123") or "admin123"
    existing = get_user_by_username(username)
    if existing:
        return {"ok": True, "created": False, "user": _public_user(existing)}
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, status, display_name)
            VALUES (%s, %s, 'admin', 'active', %s)
            RETURNING *
            """,
            (username, hash_password(password), username),
        ).fetchone()
    return {"ok": True, "created": True, "user": _public_user(dict(row))}


def register_user(
    *,
    username: str,
    password: str,
    email: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    ensure_schema()
    username = (username or "").strip()
    password = password or ""
    email = (email or "").strip() or None
    if not USERNAME_RE.match(username):
        raise ValueError("用户名需 3–32 位字母/数字/下划线")
    if len(password) < 6:
        raise ValueError("密码至少 6 位")
    if email and ("@" not in email or len(email) > 120):
        raise ValueError("邮箱格式不正确")
    if get_user_by_username(username):
        raise ValueError("用户名已存在")
    with get_conn() as conn:
        if email:
            taken = conn.execute(
                "SELECT 1 FROM users WHERE email = %s",
                (email,),
            ).fetchone()
            if taken:
                raise ValueError("邮箱已被占用")
        row = conn.execute(
            """
            INSERT INTO users (username, email, password_hash, role, status, display_name)
            VALUES (%s, %s, %s, 'user', 'active', %s)
            RETURNING *
            """,
            (username, email, hash_password(password), display_name or username),
        ).fetchone()
    user = _public_user(dict(row))
    return {"ok": True, "user": user, "token": issue_token(user)}


def login_user(*, username: str, password: str) -> dict[str, Any]:
    ensure_schema()
    username = (username or "").strip()
    row = get_user_by_username(username)
    if not row or not verify_password(password, row["password_hash"]):
        raise ValueError("用户名或密码错误")
    if row.get("status") != "active":
        raise ValueError("账号已停用")
    user = _public_user(row)
    return {"ok": True, "user": user, "token": issue_token(user)}


def issue_token(user: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(days=_jwt_expire_days()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])


def user_from_authorization(header: str | None) -> dict[str, Any] | None:
    if dev_skip_auth():
        return {
            "id": 0,
            "username": "dev",
            "email": None,
            "role": "admin",
            "status": "active",
            "display_name": "开发跳过登录",
            "ai_quota_daily": 999,
            "created_at": None,
        }
    if not header:
        return None
    parts = header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        payload = decode_token(parts[1].strip())
        uid = int(payload["sub"])
    except Exception:
        return None
    row = get_user_by_id(uid)
    if not row or row.get("status") != "active":
        return None
    return _public_user(row)


def me_response(header: str | None) -> dict[str, Any]:
    user = user_from_authorization(header)
    if not user:
        raise PermissionError("未登录或 token 无效")
    return {
        "ok": True,
        "user": user,
        "dev_skip_auth": dev_skip_auth(),
    }
