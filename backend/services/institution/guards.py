# -*- coding: utf-8 -*-
"""机构端通用守卫：审计、成员解析、角色校验。

与具体业务无关，company/research/proposal 等模块都可以引用。
"""
from __future__ import annotations

import uuid
from typing import Any

from .common import _j

POLICY_VERSION = "inst-policy-v1"


class AiUnavailable(RuntimeError):
    """AI 未配置/不可用；由路由层映射为 503。"""


def _audit(
    conn,
    *,
    org_id: int,
    actor_member_id: int | None,
    action: str,
    object_type: str,
    object_id: int | None,
    before: Any = None,
    after: Any = None,
    ip: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO inst_audit_event
          (org_id, actor_member_id, action, object_type, object_id, before, after, policy_version, ip)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            org_id,
            actor_member_id,
            action,
            object_type,
            object_id,
            _j(before) if before is not None else None,
            _j(after) if after is not None else None,
            POLICY_VERSION,
            ip,
        ),
    )


def _member(conn, org_id: int, member_id: int | None) -> dict[str, Any] | None:
    if not member_id:
        return None
    row = conn.execute(
        "SELECT id, org_id, role, status, title_cn FROM inst_members WHERE id=%s AND org_id=%s AND status='active'",
        (member_id, org_id),
    ).fetchone()
    return dict(row) if row else None


def _require_role(member: dict[str, Any] | None, *roles: str) -> None:
    if not member or member.get("role") not in roles:
        raise PermissionError("当前角色无权执行该操作")


def _uid() -> str:
    return uuid.uuid4().hex[:8]


