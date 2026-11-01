# -*- coding: utf-8 -*-
"""账号注销：密码/确认词校验 + 匿名化与数据清理。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.auth.account_store import delete_account, validate_deletion_request  # noqa: E402
from services.auth.auth_store import get_user_by_id, hash_password, register_user  # noqa: E402
from services.core.db import get_conn  # noqa: E402


def test_validate_requires_password_and_confirm() -> None:
    digest = hash_password("secret123")
    with pytest.raises(ValueError):
        validate_deletion_request(username="u1", password_hash=digest, password="", confirm="u1")
    with pytest.raises(PermissionError):
        validate_deletion_request(username="u1", password_hash=digest, password="wrong", confirm="u1")
    with pytest.raises(ValueError):
        validate_deletion_request(username="u1", password_hash=digest, password="secret123", confirm="yes")
    validate_deletion_request(username="u1", password_hash=digest, password="secret123", confirm="u1")
    validate_deletion_request(username="u1", password_hash=digest, password="secret123", confirm="注销")


def test_delete_account_anonymizes_and_purges() -> None:
    username = f"del{uuid.uuid4().hex[:10]}"
    user = register_user(username=username, password="secret123", email=f"{username}@example.com")["user"]
    try:
        out = delete_account(user["id"], password="secret123", confirm=username)
        assert out["ok"] is True
        assert out["username"].startswith(f"deleted_{user['id']}")
        row = get_user_by_id(user["id"])
        assert row is not None
        assert row["status"] == "disabled"
        assert row["email"] is None
        assert row["display_name"] == "已注销用户"
        assert row["password_hash"] == "!"
        # 重复注销会被拒绝
        with pytest.raises(ValueError):
            delete_account(user["id"], password="secret123", confirm=out["username"])
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id=%s", (user["id"],))


def test_delete_unknown_user() -> None:
    with pytest.raises(LookupError):
        delete_account(10**12, password="x", confirm="x")
