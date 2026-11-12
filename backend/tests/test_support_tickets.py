# -*- coding: utf-8 -*-
"""H14：客服工单（提交 / 回复 / 关闭 / 权限边界）。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.support import support_store as store  # noqa: E402

ensure_schema()


def _user(role: str = "user") -> int:
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s,'!',%s) RETURNING id",
            (f"ticket_{uuid.uuid4().hex[:8]}", role),
        ).fetchone()
    return int(row["id"])


def test_ticket_lifecycle() -> None:
    user_id = _user()
    admin_id = _user("admin")
    try:
        ticket = store.create_ticket(user_id, category="account", subject="无法找回密码", body="邮箱收不到重置邮件")
        assert ticket["status"] == "open"
        listed = store.list_my_tickets(user_id)
        assert listed["total"] == 1

        replied = store.add_user_reply(user_id, ticket["id"], "补充：邮箱是 qq 邮箱")
        assert len(replied["replies"]) == 1

        admin_view = store.admin_reply(admin_id, ticket["id"], "请检查垃圾箱", status="in_progress")
        assert admin_view["status"] == "in_progress"
        assert len(admin_view["replies"]) == 2

        closed = store.admin_reply(admin_id, ticket["id"], "已处理", status="closed")
        assert closed["status"] == "closed"
        with pytest.raises(ValueError):
            store.add_user_reply(user_id, ticket["id"], "再问一句")
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id IN (%s,%s)", (user_id, admin_id))


def test_validation_and_ownership() -> None:
    user_id = _user()
    other_id = _user()
    try:
        with pytest.raises(ValueError):
            store.create_ticket(user_id, category="bad", subject="x", body="y")
        with pytest.raises(ValueError):
            store.create_ticket(user_id, category="other", subject="x", body="y")
        ticket = store.create_ticket(user_id, category="other", subject="发票问题", body="需要发票")
        with pytest.raises(KeyError):
            store.get_my_ticket(other_id, ticket["id"])
        with pytest.raises(KeyError):
            store.add_user_reply(other_id, ticket["id"], "越权回复")
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id IN (%s,%s)", (user_id, other_id))


def test_routes_registered() -> None:
    paths = app.openapi().get("paths") or {}
    for path, method in [
        ("/api/support/tickets", "post"),
        ("/api/support/tickets/{ticket_id}/replies", "post"),
        ("/api/admin/support/tickets", "get"),
        ("/api/admin/support/tickets/{ticket_id}/replies", "post"),
    ]:
        assert path in paths and method in paths[path], f"缺少 {method.upper()} {path}"
