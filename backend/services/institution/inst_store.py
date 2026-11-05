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
    "quant_researcher": ("量化研究员", "Quant researcher"),
    "quant_reviewer": ("量化研究复核", "Quant research reviewer"),
}

# 机构量化成员只使用 /api/inst/quant/*；对主观投资九工作区一律无权限。
# 这是产品线隔离，不是“只靠前端隐藏”：服务端权限矩阵全部为 none。
QUANT_ROLES = frozenset({"quant_researcher", "quant_reviewer"})

# 九个工作区，与需求文档 §2.2 一致
WORKSPACE_LABELS: dict[str, tuple[str, str]] = {
    "overview": ("投资总览", "Investment overview"),
    "ideas": ("机会发现", "Discovery"),
    "research": ("公司研究", "Research"),
    "debate": ("投资辩论室", "Debate room"),
    "approvals": ("投委会审批", "IC approvals"),
    "execution": ("交易执行", "Execution"),
    "portfolio": ("投资管理", "Investment management"),
    "monitor": ("投后管理", "Post-investment"),
    "about": ("Agent管理", "Agent management"),
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
    "quant_researcher": {key: "none" for key in WORKSPACES},
    "quant_reviewer": {key: "none" for key in WORKSPACES},
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
                role IN ('manager', 'partner', 'chairman', 'risk', 'execution', 'monitoring', 'quant_researcher', 'quant_reviewer')
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
    # 注意：row 是 inst_members JOIN inst_orgs 的结果，`id` 是成员 ID，
    # 机构 ID 必须取 `org_id`；否则第二个及之后的成员会把机构 ID 错认成成员 ID。
    return {
        "id": int(row.get("org_id") or 0),
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


def issue_quant_token(
    user: dict[str, Any], membership: dict[str, Any], *, org_id: int | None = None
) -> str:
    """机构量化会话：scope 仍是 inst，但 product=quant，只给 quant API 使用。"""
    role = str(membership.get("role") or "")
    if role not in QUANT_ROLES:
        raise PermissionError("该账号没有机构量化权限")
    return issue_token(
        user,
        extra={
            "scope": "inst",
            "product": "quant",
            "org_id": int(org_id if org_id is not None else membership["org_id"]),
            "inst_role": role,
        },
    )


def login_inst(*, username: str, password: str) -> dict[str, Any]:
    """校验账号密码并确认机构成员身份；失败抛 ValueError（调用方转 HTTP）。"""
    user = authenticate_user(username=username, password=password)
    membership = get_membership(int(user["id"]))
    if not membership:
        raise PermissionError("该账号未加入机构，请联系管理员")
    if str(membership.get("role") or "") in QUANT_ROLES:
        raise PermissionError("该账号为机构量化角色，请使用机构量化入口登录")
    token = issue_inst_token(user, membership)
    return {"user": user, "membership": membership, "token": token}


def login_quant(*, username: str, password: str) -> dict[str, Any]:
    """机构量化入口：必须是 active 成员且角色在 QUANT_ROLES。"""
    user = authenticate_user(username=username, password=password)
    membership = get_membership(int(user["id"]))
    if not membership or str(membership.get("role") or "") not in QUANT_ROLES:
        raise PermissionError("该账号没有机构量化权限")
    token = issue_quant_token(user, membership)
    return {"user": user, "membership": membership, "token": token}


def _demo_mode() -> bool:
    return (env("INST_DEMO_MODE", "1") or "1").strip() not in {"0", "false", "False", "no"}


def _context(user: dict[str, Any], membership: dict[str, Any]) -> dict[str, Any]:
    role = str(membership["role"])
    label_cn, label_en = ROLE_LABELS.get(role, (role, role))
    return {
        "user": user,
        "member_id": int(membership.get("id") or 0),
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


def _quant_context(user: dict[str, Any], membership: dict[str, Any]) -> dict[str, Any]:
    role = str(membership.get("role") or "")
    label_cn, label_en = ROLE_LABELS.get(role, (role, role))
    return {
        "product": "quant",
        "quant": True,
        "user": user,
        "member_id": int(membership.get("id") or 0),
        "org": _org_payload(membership),
        "role": role,
        "role_label_cn": label_cn,
        "role_label_en": label_en,
        # 第一期量化资产按 user_id 隔离，不把成员私有数据伪装成机构共享。
        "visibility": "member_private",
        "permissions": {
            "quant": "review" if role == "quant_reviewer" else "write",
        },
        "can_review": role == "quant_reviewer",
        "can_write": role == "quant_researcher",
        "workspaces": [],
        "demo": _demo_mode(),
    }


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
        if payload.get("scope") != "inst" or payload.get("product") == "quant":
            return None
        uid = int(payload["sub"])
    except Exception:
        return None
    user_row = get_user_by_id(uid)
    if not user_row or user_row.get("status") != "active":
        return None
    user = user_from_authorization(header, allow_inst=True)
    if not user:
        return None
    # 角色以数据库为准，令牌里的 inst_role 只作签发时的快照
    membership = get_membership(uid, payload.get("org_id"))
    if not membership:
        return None
    return _context(user, membership)


def user_from_quant_authorization(header: str | None) -> dict[str, Any] | None:
    """解析机构量化令牌；个人令牌和主观机构令牌都不能进入量化 API。"""
    if dev_skip_auth():
        ctx = _dev_context()
        ctx.update({"product": "quant", "quant": True, "visibility": "member_private"})
        ctx["permissions"] = {"quant": "write"}
        ctx["workspaces"] = []
        return ctx
    if not header:
        return None
    parts = header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        payload = decode_token(parts[1].strip())
        if payload.get("scope") != "inst" or payload.get("product") != "quant":
            return None
        uid = int(payload["sub"])
    except Exception:
        return None
    user_row = get_user_by_id(uid)
    if not user_row or user_row.get("status") != "active":
        return None
    user = user_from_authorization(header, allow_quant=True)
    if not user:
        return None
    # 每次请求实时回查成员/机构/角色，停用立即失效。
    membership = get_membership(uid, payload.get("org_id"))
    if not membership or str(membership.get("role") or "") not in QUANT_ROLES:
        return None
    return _quant_context(user, membership)


def me_payload(context: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **context}


def login_payload(result: dict[str, Any]) -> dict[str, Any]:
    ctx = _context(result["user"], result["membership"])
    return {"ok": True, "token": result["token"], **ctx}


def login_quant_payload(result: dict[str, Any]) -> dict[str, Any]:
    ctx = _quant_context(result["user"], result["membership"])
    return {"ok": True, "token": result["token"], **ctx}


def list_memberships(user_id: int) -> list[dict[str, Any]]:
    """用户可用的全部机构成员关系（S02 多机构）。"""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.org_id, m.role, m.status AS member_status, m.title_cn,
                   o.code, o.name_cn, o.name_en, o.status AS org_status
              FROM inst_members m
              JOIN inst_orgs o ON o.id = m.org_id
             WHERE m.user_id = %s AND m.status = 'active' AND o.status = 'active'
             ORDER BY m.org_id, m.id
            """,
            (int(user_id),),
        ).fetchall()
    return [dict(r) for r in rows]


def session_payload(user: dict[str, Any], membership: dict[str, Any]) -> dict[str, Any]:
    """机构登录/SSO 统一返回体。"""
    token = issue_inst_token(user, membership)
    return {
        "user": user,
        "membership": membership,
        "token": token,
        "context": _context(user, membership),
    }
