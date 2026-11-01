# -*- coding: utf-8 -*-
"""P01/P02/P03/P04/P05：组织、套餐、额度、人工账单与资产隔离。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from services.auth.auth_store import ensure_schema  # noqa: E402
from services.billing import billing_store as billing  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.research import asset_store  # noqa: E402

ensure_schema()


def _user(role: str = "user") -> tuple[int, str]:
    name = f"org_{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s,'!',%s) RETURNING id",
            (name, role),
        ).fetchone()
    return int(row["id"]), name


def test_org_plan_credits_and_billing_request() -> None:
    owner_id, _ = _user()
    member_id, member_name = _user()
    outsider_id, _ = _user()
    admin_id, _ = _user("admin")
    try:
        org = billing.create_org(owner_id, name="研究小组")
        org_id = int(org["id"])
        assert billing.get_org(owner_id, org_id)["plan_code"] == "free"

        billing.add_member(org_id, owner_id, username=member_name, role="member")
        with pytest.raises(PermissionError):
            billing.get_org(outsider_id, org_id)

        pro = billing.set_plan(owner_id, org_id, plan_code="pro")
        assert pro["plan_code"] == "pro" and pro["ai_daily_quota"] == 1000
        with pytest.raises(PermissionError):
            billing.set_plan(member_id, org_id, plan_code="team")

        billing.grant_credits(org_id=org_id, user_id=None, delta=500, reason="初始化", created_by=admin_id)
        assert billing.credits_balance(org_id) == 500

        request = billing.request_billing(
            member_id, org_id, kind="topup", amount_cents=9900, note="充值"
        )
        assert request["status"] == "pending"
        approved = billing.resolve_billing_request(
            int(request["id"]), status="approved", admin_id=admin_id
        )
        assert approved["status"] == "approved"
        assert billing.credits_balance(org_id) == 500 + 9900

        with pytest.raises(ValueError):
            billing.resolve_billing_request(int(request["id"]), status="approved", admin_id=admin_id)
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM app_orgs WHERE owner_id=%s", (owner_id,))
            conn.execute("DELETE FROM users WHERE id IN (%s,%s,%s,%s)", (owner_id, member_id, outsider_id, admin_id))


def test_assets_are_scoped_by_org() -> None:
    owner_id, _ = _user()
    member_id, member_name = _user()
    outsider_id, _ = _user()
    try:
        org = billing.create_org(owner_id, name="资产小组")
        org_id = int(org["id"])
        billing.add_member(org_id, owner_id, username=member_name, role="member")

        shared = asset_store.create_universe(
            owner_id, name="团队池", symbols=["600519.SH"], org_id=org_id
        )
        personal = asset_store.create_universe(owner_id, name="个人池", symbols=["000858.SZ"])

        assert [a["id"] for a in asset_store.list_universes(owner_id, org_id=org_id)] == [shared["id"]]
        assert [a["id"] for a in asset_store.list_universes(owner_id)] == [personal["id"]]
        # 成员可读组织资产；外人不可
        assert asset_store.get_universe(member_id, shared["id"])["snapshot"]["symbols"] == ["600519.SH"]
        with pytest.raises(KeyError):
            asset_store.get_universe(outsider_id, shared["id"])
        with pytest.raises(PermissionError):
            asset_store.create_universe(outsider_id, name="越权", symbols=["600519.SH"], org_id=org_id)
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM app_orgs WHERE owner_id=%s", (owner_id,))
            conn.execute("DELETE FROM users WHERE id IN (%s,%s,%s)", (owner_id, member_id, outsider_id))


def test_billing_routes_registered() -> None:
    paths = app.openapi().get("paths") or {}
    for path in (
        "/api/orgs",
        "/api/orgs/{org_id}/members",
        "/api/orgs/{org_id}/plan",
        "/api/orgs/{org_id}/billing/requests",
        "/api/admin/billing/requests/{request_id}/resolve",
        "/api/admin/billing/credits",
    ):
        assert path in paths, f"缺少 {path}"
