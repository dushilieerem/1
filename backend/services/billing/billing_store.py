# -*- coding: utf-8 -*-
"""组织、套餐与额度（P01/P03/P05）。

产品默认（未接在线支付前）：
- 套餐：free / pro / team，由管理员或组织 owner 调整；
- 充值/发票：走人工工单（billing request），管理员审批后入账；
- 额度：credits 以“分”为单位记账，余额 = ledger 求和。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from services.core.db import get_conn

PLAN_SEED: tuple[dict[str, Any], ...] = (
    {
        "code": "free",
        "name_cn": "免费版",
        "name_en": "Free",
        "price_cents": 0,
        "ai_daily_quota": 100,
        "universe_limit": 5,
        "features": {"team": False, "export": False},
    },
    {
        "code": "pro",
        "name_cn": "专业版",
        "name_en": "Pro",
        "price_cents": 9900,
        "ai_daily_quota": 1000,
        "universe_limit": 50,
        "features": {"team": False, "export": True},
    },
    {
        "code": "team",
        "name_cn": "团队版",
        "name_en": "Team",
        "price_cents": 29900,
        "ai_daily_quota": 5000,
        "universe_limit": 200,
        "features": {"team": True, "export": True},
    },
)

ORG_ROLES = {"owner", "admin", "member"}
REQUEST_KINDS = {"topup", "invoice"}
REQUEST_STATUSES = {"pending", "approved", "rejected"}


def ensure_billing_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_plans (
              code            TEXT PRIMARY KEY,
              name_cn         TEXT NOT NULL,
              name_en         TEXT NOT NULL,
              price_cents     INTEGER NOT NULL DEFAULT 0,
              ai_daily_quota  INTEGER NOT NULL DEFAULT 100,
              universe_limit  INTEGER NOT NULL DEFAULT 5,
              features        JSONB NOT NULL DEFAULT '{}'::jsonb,
              active          BOOLEAN NOT NULL DEFAULT TRUE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_orgs (
              id          BIGSERIAL PRIMARY KEY,
              code        TEXT NOT NULL UNIQUE,
              name        TEXT NOT NULL,
              owner_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              plan_code   TEXT NOT NULL REFERENCES app_plans(code),
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_org_members (
              org_id      BIGINT NOT NULL REFERENCES app_orgs(id) ON DELETE CASCADE,
              user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              role        TEXT NOT NULL DEFAULT 'member',
              status      TEXT NOT NULL DEFAULT 'active',
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (org_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_credit_ledger (
              id          BIGSERIAL PRIMARY KEY,
              org_id      BIGINT REFERENCES app_orgs(id) ON DELETE CASCADE,
              user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
              delta       BIGINT NOT NULL,
              reason      TEXT NOT NULL,
              ref         TEXT,
              created_by  BIGINT,
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_billing_requests (
              id             BIGSERIAL PRIMARY KEY,
              org_id         BIGINT NOT NULL REFERENCES app_orgs(id) ON DELETE CASCADE,
              user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              kind           TEXT NOT NULL,
              amount_cents   BIGINT NOT NULL DEFAULT 0,
              note           TEXT NOT NULL DEFAULT '',
              status         TEXT NOT NULL DEFAULT 'pending',
              resolved_by    BIGINT,
              resolved_at    TIMESTAMPTZ,
              created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT app_billing_kind_chk CHECK (kind IN ('topup','invoice')),
              CONSTRAINT app_billing_status_chk CHECK (status IN ('pending','approved','rejected'))
            )
            """
        )
        for plan in PLAN_SEED:
            conn.execute(
                """
                INSERT INTO app_plans (code, name_cn, name_en, price_cents, ai_daily_quota, universe_limit, features)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (code) DO NOTHING
                """,
                (
                    plan["code"],
                    plan["name_cn"],
                    plan["name_en"],
                    plan["price_cents"],
                    plan["ai_daily_quota"],
                    plan["universe_limit"],
                    json.dumps(plan["features"], ensure_ascii=False),
                ),
            )


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("created_at", "updated_at", "resolved_at"):
        out[key] = _iso(out.get(key))
    return out


def list_plans() -> list[dict[str, Any]]:
    ensure_billing_schema()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM app_plans WHERE active ORDER BY price_cents").fetchall()
    return [_row(dict(r)) for r in rows]


def _org_row(conn, org_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT o.*, p.name_cn AS plan_name_cn, p.name_en AS plan_name_en,
               p.ai_daily_quota, p.universe_limit, p.features,
               COALESCE((SELECT SUM(delta) FROM app_credit_ledger l WHERE l.org_id=o.id), 0) AS credits
          FROM app_orgs o JOIN app_plans p ON p.code=o.plan_code
         WHERE o.id=%s
        """,
        (org_id,),
    ).fetchone()
    return _row(dict(row)) if row else None


def _member(conn, org_id: int, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM app_org_members WHERE org_id=%s AND user_id=%s AND status='active'",
        (org_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def _require_member(conn, org_id: int, user_id: int, *roles: str) -> dict[str, Any]:
    row = _member(conn, org_id, user_id)
    if not row:
        raise PermissionError("不是该组织成员")
    if roles and row["role"] not in roles:
        raise PermissionError("权限不足")
    return row


def create_org(owner_id: int, *, name: str) -> dict[str, Any]:
    ensure_billing_schema()
    title = (name or "").strip()
    if not (1 <= len(title) <= 60):
        raise ValueError("组织名称需 1–60 字")
    with get_conn() as conn:
        code = f"org-{uuid.uuid4().hex[:10]}"
        row = conn.execute(
            "INSERT INTO app_orgs (code, name, owner_id, plan_code) VALUES (%s,%s,%s,'free') RETURNING *",
            (code, title, int(owner_id)),
        ).fetchone()
        org_id = int(row["id"])
        conn.execute(
            "INSERT INTO app_org_members (org_id, user_id, role) VALUES (%s,%s,'owner')",
            (org_id, int(owner_id)),
        )
        return _org_row(conn, org_id) or {}


def list_my_orgs(user_id: int) -> list[dict[str, Any]]:
    ensure_billing_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT o.id FROM app_orgs o
              JOIN app_org_members m ON m.org_id=o.id AND m.user_id=%s AND m.status='active'
             ORDER BY o.id
            """,
            (int(user_id),),
        ).fetchall()
        out = []
        for row in rows:
            org = _org_row(conn, int(row["id"])) or {}
            membership = _member(conn, int(row["id"]), int(user_id)) or {}
            org["my_role"] = membership.get("role")
            out.append(org)
    return out


def get_org(user_id: int, org_id: int) -> dict[str, Any]:
    ensure_billing_schema()
    with get_conn() as conn:
        _require_member(conn, org_id, user_id)
        org = _org_row(conn, org_id)
        if not org:
            raise LookupError("组织不存在")
        members = conn.execute(
            """
            SELECT m.user_id, m.role, m.status, m.created_at, u.username, u.display_name
              FROM app_org_members m JOIN users u ON u.id=m.user_id
             WHERE m.org_id=%s ORDER BY m.created_at
            """,
            (org_id,),
        ).fetchall()
        org["members"] = [_row(dict(r)) for r in members]
    return org


def add_member(org_id: int, actor_id: int, *, username: str, role: str = "member") -> dict[str, Any]:
    ensure_billing_schema()
    if role not in ORG_ROLES - {"owner"}:
        raise ValueError("角色只能是 admin/member")
    with get_conn() as conn:
        _require_member(conn, org_id, actor_id, "owner", "admin")
        user = conn.execute(
            "SELECT id, username FROM users WHERE username=%s AND status='active'", (username.strip(),)
        ).fetchone()
        if not user:
            raise LookupError("用户不存在")
        exists = conn.execute(
            "SELECT 1 FROM app_org_members WHERE org_id=%s AND user_id=%s", (org_id, user["id"])
        ).fetchone()
        if exists:
            raise ValueError("该用户已在组织中")
        conn.execute(
            "INSERT INTO app_org_members (org_id, user_id, role) VALUES (%s,%s,%s)",
            (org_id, user["id"], role),
        )
    return get_org(actor_id, org_id)


def remove_member(org_id: int, actor_id: int, user_id: int) -> dict[str, Any]:
    ensure_billing_schema()
    with get_conn() as conn:
        actor = _require_member(conn, org_id, actor_id, "owner", "admin")
        target = _member(conn, org_id, user_id)
        if not target:
            raise LookupError("成员不存在")
        if target["role"] == "owner":
            raise PermissionError("不能移除 owner")
        if actor["role"] == "admin" and target["role"] == "admin":
            raise PermissionError("admin 不能移除 admin")
        conn.execute(
            "UPDATE app_org_members SET status='disabled' WHERE org_id=%s AND user_id=%s",
            (org_id, user_id),
        )
    return get_org(actor_id, org_id)


def set_plan(user_id: int, org_id: int, *, plan_code: str) -> dict[str, Any]:
    ensure_billing_schema()
    with get_conn() as conn:
        _require_member(conn, org_id, user_id, "owner", "admin")
        plan = conn.execute(
            "SELECT code FROM app_plans WHERE code=%s AND active", (plan_code,)
        ).fetchone()
        if not plan:
            raise ValueError("套餐不存在")
        conn.execute(
            "UPDATE app_orgs SET plan_code=%s, updated_at=NOW() WHERE id=%s", (plan_code, org_id)
        )
        return _org_row(conn, org_id) or {}


def grant_credits(
    *, org_id: int | None, user_id: int | None, delta: int, reason: str, created_by: int | None
) -> dict[str, Any]:
    ensure_billing_schema()
    if delta == 0:
        raise ValueError("delta 不能为 0")
    if not org_id and not user_id:
        raise ValueError("必须指定 org_id 或 user_id")
    with get_conn() as conn:
        if org_id:
            exists = conn.execute("SELECT 1 FROM app_orgs WHERE id=%s", (org_id,)).fetchone()
            if not exists:
                raise LookupError("组织不存在")
        if user_id:
            exists = conn.execute("SELECT 1 FROM users WHERE id=%s", (user_id,)).fetchone()
            if not exists:
                raise LookupError("用户不存在")
        row = conn.execute(
            "INSERT INTO app_credit_ledger (org_id, user_id, delta, reason, created_by) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING *",
            (org_id, user_id, int(delta), (reason or "manual")[:120], created_by),
        ).fetchone()
    return _row(dict(row))


def credits_balance(org_id: int) -> int:
    ensure_billing_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta),0) AS n FROM app_credit_ledger WHERE org_id=%s", (org_id,)
        ).fetchone()
    return int(row["n"] or 0)


def list_credits(user_id: int, org_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    ensure_billing_schema()
    with get_conn() as conn:
        _require_member(conn, org_id, user_id)
        rows = conn.execute(
            "SELECT * FROM app_credit_ledger WHERE org_id=%s ORDER BY created_at DESC LIMIT %s",
            (org_id, max(1, min(limit, 200))),
        ).fetchall()
    return [_row(dict(r)) for r in rows]


def request_billing(
    user_id: int, org_id: int, *, kind: str, amount_cents: int, note: str = ""
) -> dict[str, Any]:
    ensure_billing_schema()
    if kind not in REQUEST_KINDS:
        raise ValueError("kind 必须是 topup/invoice")
    if amount_cents < 0:
        raise ValueError("金额不能为负")
    with get_conn() as conn:
        _require_member(conn, org_id, user_id)
        row = conn.execute(
            "INSERT INTO app_billing_requests (org_id, user_id, kind, amount_cents, note) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING *",
            (org_id, int(user_id), kind, int(amount_cents), (note or "")[:500]),
        ).fetchone()
    return _row(dict(row))


def list_billing_requests(user_id: int, org_id: int) -> list[dict[str, Any]]:
    ensure_billing_schema()
    with get_conn() as conn:
        _require_member(conn, org_id, user_id)
        rows = conn.execute(
            "SELECT * FROM app_billing_requests WHERE org_id=%s ORDER BY created_at DESC LIMIT 100",
            (org_id,),
        ).fetchall()
    return [_row(dict(r)) for r in rows]


def admin_list_billing_requests(status: str | None = None) -> list[dict[str, Any]]:
    ensure_billing_schema()
    if status and status not in REQUEST_STATUSES:
        raise ValueError("status 不合法")
    with get_conn() as conn:
        sql = (
            "SELECT r.*, o.name AS org_name, u.username FROM app_billing_requests r "
            "JOIN app_orgs o ON o.id=r.org_id JOIN users u ON u.id=r.user_id"
        )
        params: list[Any] = []
        if status:
            sql += " WHERE r.status=%s"
            params.append(status)
        sql += " ORDER BY r.created_at DESC LIMIT 200"
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row(dict(r)) for r in rows]


def resolve_billing_request(
    request_id: int, *, status: str, admin_id: int, note: str = ""
) -> dict[str, Any]:
    ensure_billing_schema()
    if status not in {"approved", "rejected"}:
        raise ValueError("status 必须是 approved/rejected")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM app_billing_requests WHERE id=%s", (request_id,)
        ).fetchone()
        if not row:
            raise LookupError("申请不存在")
        if row["status"] != "pending":
            raise ValueError("该申请已处理")
        conn.execute(
            "UPDATE app_billing_requests SET status=%s, resolved_by=%s, resolved_at=NOW(), "
            "note = CASE WHEN %s = '' THEN note ELSE %s END WHERE id=%s",
            (status, admin_id, note, note, request_id),
        )
        if status == "approved" and int(row["amount_cents"]) > 0:
            conn.execute(
                "INSERT INTO app_credit_ledger (org_id, user_id, delta, reason, ref, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    int(row["org_id"]),
                    None,
                    int(row["amount_cents"]),
                    f"{row['kind']} approved",
                    f"request:{request_id}",
                    admin_id,
                ),
            )
        updated = conn.execute(
            "SELECT * FROM app_billing_requests WHERE id=%s", (request_id,)
        ).fetchone()
    return _row(dict(updated))
