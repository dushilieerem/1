# -*- coding: utf-8 -*-
"""机构端存储与权限（PostgreSQL）。

职责边界：
- 组织/成员/角色落库，独立于 `users.role`（避免破坏个人版 user/admin 约束）。
- 权限矩阵在本文件定义，服务端计算；前端菜单显隐只是展示，不是安全边界。
- 机构令牌 claims 带 `scope=inst`，由 `user_from_inst_authorization` 校验。
"""
from __future__ import annotations

from typing import Any

from services.auth.auth_store import (
    authenticate_user,
    decode_token,
    dev_skip_auth,
    get_user_by_id,
    hash_password,
    issue_token,
    user_from_authorization,
)
from services.core.db import get_conn
from services.core.env_config import env

# 六个机构角色，与需求文档 §2.1 一致
ROLE_LABELS: dict[str, tuple[str, str]] = {
    "manager": ("投资经理", "Investment manager"),
    "partner": ("合伙人", "Partner"),
    "chairman": ("Chairman", "Chairman"),
    "risk": ("独立风控", "Independent risk"),
    "execution": ("交易执行", "Execution"),
    "monitoring": ("组合监控", "Portfolio monitoring"),
}

# 九个工作区，与需求文档 §2.2 一致
WORKSPACE_LABELS: dict[str, tuple[str, str]] = {
    "overview": ("投资驾驶舱", "Overview"),
    "ideas": ("机会发现", "Discovery"),
    "research": ("公司研究", "Research"),
    "debate": ("投资辩论室", "Debate room"),
    "portfolio": ("投资组合", "Portfolio"),
    "approvals": ("投委会与审批", "IC & approvals"),
    "execution": ("交易执行", "Execution"),
    "monitor": ("投后与退出", "Monitoring & exits"),
    "about": ("关于我们", "About us"),
}

# write = 可写与操作；read = 只读；digest = 仅关联摘要；none = 无权限且菜单隐藏
Access = str
WORKSPACES: tuple[str, ...] = tuple(WORKSPACE_LABELS)

ROLE_WORKSPACE_ACCESS: dict[str, dict[str, Access]] = {
    "manager": {
        "overview": "read",
        "ideas": "write",
        "research": "write",
        "debate": "write",
        "portfolio": "read",
        "approvals": "write",
        "execution": "read",
        "monitor": "write",
        "about": "read",
    },
    "partner": {
        "overview": "read",
        "ideas": "read",
        "research": "read",
        "debate": "read",
        "portfolio": "write",
        "approvals": "write",
        "execution": "read",
        "monitor": "write",
        "about": "read",
    },
    "chairman": {
        "overview": "read",
        "ideas": "none",
        "research": "digest",
        "debate": "digest",
        "portfolio": "read",
        "approvals": "write",
        "execution": "digest",
        "monitor": "read",
        "about": "read",
    },
    "risk": {
        "overview": "read",
        "ideas": "none",
        "research": "read",
        "debate": "read",
        "portfolio": "write",
        "approvals": "write",
        "execution": "write",
        "monitor": "write",
        "about": "read",
    },
    "execution": {
        "overview": "read",
        "ideas": "none",
        "research": "none",
        "debate": "none",
        "portfolio": "read",
        "approvals": "read",
        "execution": "write",
        "monitor": "read",
        "about": "read",
    },
    "monitoring": {
        "overview": "read",
        "ideas": "none",
        "research": "digest",
        "debate": "none",
        "portfolio": "write",
        "approvals": "digest",
        "execution": "read",
        "monitor": "write",
        "about": "read",
    },
}

DEMO_ORG = {
    "code": "sunvalley",
    "name_cn": "旸谷资本",
    "name_en": "Sunvalley Capital",
}

# (username, display_name, role)
DEMO_MEMBERS: tuple[tuple[str, str, str], ...] = (
    ("inst_manager", "投资经理", "manager"),
    ("inst_partner", "合伙人", "partner"),
    ("inst_chairman", "Chairman", "chairman"),
    ("inst_risk", "独立风控", "risk"),
    ("inst_execution", "交易执行", "execution"),
    ("inst_monitoring", "组合监控", "monitoring"),
)


# ---------------------------------------------------------------- 权限


def permissions_for(role: str) -> dict[str, Access]:
    """返回角色的九工作区权限；未知角色一律无权限（fail closed）。"""
    matrix = ROLE_WORKSPACE_ACCESS.get(role) or {}
    return {key: matrix.get(key, "none") for key in WORKSPACES}


def workspaces_for(role: str) -> list[dict[str, Any]]:
    perms = permissions_for(role)
    out: list[dict[str, Any]] = []
    for key in WORKSPACES:
        label_cn, label_en = WORKSPACE_LABELS[key]
        out.append(
            {
                "key": key,
                "label_cn": label_cn,
                "label_en": label_en,
                "path": f"/inst/{key}",
                "access": perms[key],
                "visible": perms[key] != "none",
            }
        )
    return out


def can_access(role: str, workspace: str) -> bool:
    return permissions_for(role).get(workspace, "none") != "none"


# ---------------------------------------------------------------- schema / seed


def ensure_inst_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inst_orgs (
              id          BIGSERIAL PRIMARY KEY,
              code        TEXT NOT NULL UNIQUE,
              name_cn     TEXT NOT NULL,
              name_en     TEXT,
              status      TEXT NOT NULL DEFAULT 'active',
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT inst_orgs_status_chk CHECK (status IN ('active', 'disabled'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inst_members (
              id          BIGSERIAL PRIMARY KEY,
              org_id      BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
              user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              role        TEXT NOT NULL,
              title_cn    TEXT,
              status      TEXT NOT NULL DEFAULT 'active',
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT inst_members_role_chk CHECK (
                role IN ('manager', 'partner', 'chairman', 'risk', 'execution', 'monitoring')
              ),
              CONSTRAINT inst_members_status_chk CHECK (status IN ('active', 'disabled')),
              CONSTRAINT inst_members_org_user_key UNIQUE (org_id, user_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inst_members_user ON inst_members (user_id, status)"
        )


def seed_inst_demo() -> dict[str, Any]:
    """幂等写入演示机构与六个角色账号；INST_SEED_DEMO=0 可关闭。"""
    if (env("INST_SEED_DEMO", "1") or "1").strip() in {"0", "false", "False", "no"}:
        return {"ok": True, "skipped": True}

    ensure_inst_schema()
    password = env("INST_DEMO_PASSWORD", "inst123456") or "inst123456"
    # 六个演示账号共用同一密码，只做一次 bcrypt
    password_hash = hash_password(password)
    created_users = 0
    with get_conn() as conn:
        org = conn.execute(
            """
            INSERT INTO inst_orgs (code, name_cn, name_en)
            VALUES (%s, %s, %s)
            ON CONFLICT (code) DO UPDATE
              SET name_cn = EXCLUDED.name_cn, name_en = EXCLUDED.name_en
            RETURNING *
            """,
            (DEMO_ORG["code"], DEMO_ORG["name_cn"], DEMO_ORG["name_en"]),
        ).fetchone()
        org_id = int(org["id"])
        for username, display_name, role in DEMO_MEMBERS:
            row = conn.execute(
                "SELECT id FROM users WHERE username = %s", (username,)
            ).fetchone()
            if not row:
                row = conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role, status, display_name)
                    VALUES (%s, %s, 'user', 'active', %s)
                    RETURNING id
                    """,
                    (username, password_hash, display_name),
                ).fetchone()
                created_users += 1
            conn.execute(
                """
                INSERT INTO inst_members (org_id, user_id, role, title_cn, status)
                VALUES (%s, %s, %s, %s, 'active')
                ON CONFLICT (org_id, user_id) DO UPDATE
                  SET role = EXCLUDED.role,
                      title_cn = EXCLUDED.title_cn,
                      status = 'active',
                      updated_at = NOW()
                """,
                (org_id, int(row["id"]), role, display_name),
            )
    return {"ok": True, "created_users": created_users, "org_id": org_id}


# ---------------------------------------------------------------- 登录 / 会话


def _org_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "code": row["code"],
        "name_cn": row["name_cn"],
        "name_en": row.get("name_en") or "",
    }


def get_membership(user_id: int, org_id: int | None = None) -> dict[str, Any] | None:
    sql = """
        SELECT m.id, m.org_id, m.role, m.status AS member_status, m.title_cn,
               o.code, o.name_cn, o.name_en, o.status AS org_status
          FROM inst_members m
          JOIN inst_orgs o ON o.id = m.org_id
         WHERE m.user_id = %s AND m.status = 'active' AND o.status = 'active'
    """
    params: tuple[Any, ...] = (user_id,)
    if org_id is not None:
        sql += " AND m.org_id = %s"
        params += (org_id,)
    sql += " ORDER BY m.id LIMIT 1"
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def issue_inst_token(
    user: dict[str, Any], membership: dict[str, Any], *, org_id: int | None = None
) -> str:
    return issue_token(
        user,
        extra={
            "scope": "inst",
            "org_id": int(org_id if org_id is not None else membership["org_id"]),
            "inst_role": membership["role"],
        },
    )


def login_inst(*, username: str, password: str) -> dict[str, Any]:
    """校验账号密码并确认机构成员身份；失败抛 ValueError（调用方转 HTTP）。"""
    user = authenticate_user(username=username, password=password)
    membership = get_membership(int(user["id"]))
    if not membership:
        raise PermissionError("该账号未加入机构，请联系管理员")
    token = issue_inst_token(user, membership)
    return {"user": user, "membership": membership, "token": token}


def _demo_mode() -> bool:
    return (env("INST_DEMO_MODE", "1") or "1").strip() not in {"0", "false", "False", "no"}


def _context(user: dict[str, Any], membership: dict[str, Any]) -> dict[str, Any]:
    role = str(membership["role"])
    label_cn, label_en = ROLE_LABELS.get(role, (role, role))
    return {
        "user": user,
        "org": _org_payload(membership),
        "role": role,
        "role_label_cn": label_cn,
        "role_label_en": label_en,
        "permissions": permissions_for(role),
        "workspaces": workspaces_for(role),
        "demo": _demo_mode(),
    }


def _dev_context() -> dict[str, Any]:
    """DEV_SKIP_AUTH 下的合成机构会话（仅本地联调，显式标记）。"""
    role = "manager"
    membership = {
        "id": 0,
        "org_id": 0,
        "role": role,
        "code": DEMO_ORG["code"],
        "name_cn": DEMO_ORG["name_cn"],
        "name_en": DEMO_ORG["name_en"],
    }
    ctx = _context(
        {
            "id": 0,
            "username": "dev",
            "display_name": "开发跳过登录",
            "role": "admin",
            "status": "active",
        },
        membership,
    )
    ctx["dev_skip_auth"] = True
    return ctx


def user_from_inst_authorization(header: str | None) -> dict[str, Any] | None:
    """解析机构令牌；个人版令牌（无 scope=inst）一律拒绝。"""
    if dev_skip_auth():
        return _dev_context()
    if not header:
        return None
    parts = header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        payload = decode_token(parts[1].strip())
        if payload.get("scope") != "inst":
            return None
        uid = int(payload["sub"])
    except Exception:
        return None
    user_row = get_user_by_id(uid)
    if not user_row or user_row.get("status") != "active":
        return None
    user = user_from_authorization(header)
    if not user:
        return None
    # 角色以数据库为准，令牌里的 inst_role 只作签发时的快照
    membership = get_membership(uid, payload.get("org_id"))
    if not membership:
        return None
    return _context(user, membership)


def me_payload(context: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **context}


def login_payload(result: dict[str, Any]) -> dict[str, Any]:
    ctx = _context(result["user"], result["membership"])
    return {"ok": True, "token": result["token"], **ctx}
