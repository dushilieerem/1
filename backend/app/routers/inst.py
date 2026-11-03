# -*- coding: utf-8 -*-
"""机构端接口：独立登录、机构会话与工作区权限。

路径前缀 `/api/inst/*` 只接受机构令牌（scope=inst）；
个人版 `/api/auth/*` 令牌不能访问这里。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.deps import require_inst_user
from services.core.audit_log_store import write_audit
from services.core.db import get_conn
from services.core.env_config import env
from services.core.rate_limit import enforce_rate_limit
from services.auth.auth_store import user_from_authorization
from services.institution.inst_store import (
    ROLE_LABELS,
    list_memberships,
    login_inst,
    login_payload,
    me_payload,
    session_payload,
)

router = APIRouter(tags=["institution"])


def _ip(request: Request) -> str | None:
    xf = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xf:
        return xf.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def _login_limit() -> int:
    try:
        return max(1, int(env("INST_LOGIN_RATE_LIMIT", "10") or "10"))
    except (TypeError, ValueError):
        return 10


@router.post("/api/inst/auth/login")
def inst_login(body: dict[str, Any], request: Request) -> dict:
    enforce_rate_limit(
        request, scope="inst.auth.login", limit=_login_limit(), window_sec=60
    )
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    try:
        result = login_inst(username=username, password=password)
    except PermissionError as exc:
        write_audit(
            action="inst.login_failed",
            username=username or None,
            module="institution",
            method="POST",
            path="/api/inst/auth/login",
            status_code=403,
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail=str(exc)[:200],
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        write_audit(
            action="inst.login_failed",
            username=username or None,
            module="institution",
            method="POST",
            path="/api/inst/auth/login",
            status_code=401,
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail=str(exc)[:200],
        )
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    payload = login_payload(result)
    user = payload.get("user") or {}
    write_audit(
        action="inst.login",
        user_id=int(user["id"]) if user.get("id") else None,
        username=str(user.get("username") or username) or None,
        role=str(payload.get("role") or ""),
        module="institution",
        method="POST",
        path="/api/inst/auth/login",
        status_code=200,
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail=f"机构端登录：{payload.get('org', {}).get('name_cn', '')} / {payload.get('role_label_cn', '')}",
    )
    return payload


@router.get("/api/inst/me")
def inst_me(ctx: dict[str, Any] = Depends(require_inst_user)) -> dict:
    return me_payload(ctx)


@router.get("/api/inst/_e2e/guard")
def inst_e2e_guard(ctx: dict[str, Any] = Depends(require_inst_user)) -> dict:
    """E2E 写库闸门：返回服务端真实库名，供写库用例判断能否落库。

    只读接口。`writable` 由 `current_database()` 是否含 `_test` / `_e2e` 计算，
    不接受客户端自证；生产库 `svquant` 永远返回 False。
    """
    with get_conn() as conn:
        row = conn.execute("SELECT current_database() AS db_name").fetchone()
    db_name = str((row or {}).get("db_name") or "")
    writable = "_test" in db_name or "_e2e" in db_name
    return {"ok": True, "db_name": db_name, "writable": writable}


def _membership_brief(m: dict[str, Any]) -> dict[str, Any]:
    label_cn, label_en = ROLE_LABELS.get(str(m.get("role")), (m.get("role"), m.get("role")))
    return {
        "org_id": int(m["org_id"]),
        "code": m.get("code"),
        "name_cn": m.get("name_cn"),
        "name_en": m.get("name_en"),
        "role": m.get("role"),
        "role_label_cn": label_cn,
        "role_label_en": label_en,
    }


@router.get("/api/inst/auth/orgs")
def inst_orgs(authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
    """列出当前登录用户可进入的机构（个人令牌或机构令牌均可）。"""
    user = user_from_authorization(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    memberships = list_memberships(int(user["id"]))
    if not memberships:
        raise HTTPException(status_code=403, detail="该账号未加入机构")
    return {"ok": True, "orgs": [_membership_brief(m) for m in memberships]}


@router.post("/api/inst/auth/sso")
def inst_sso(
    body: dict[str, Any],
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """S01：用主站令牌（或现有机构令牌）换机构会话。

    用户属于多个机构时须传 `org_id`；只属于一个机构时自动选择。
    """
    enforce_rate_limit(request, scope="inst.auth.sso", limit=_login_limit(), window_sec=60)
    raw = str(body.get("token") or "").strip()
    header = f"Bearer {raw}" if raw else authorization
    user = user_from_authorization(header)
    if not user:
        raise HTTPException(status_code=401, detail="令牌无效或用户已停用")
    memberships = list_memberships(int(user["id"]))
    if not memberships:
        raise HTTPException(status_code=403, detail="该账号未加入机构")
    org_raw = body.get("org_id")
    if org_raw is not None:
        try:
            org_id = int(org_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="org_id 不合法") from None
        membership = next((m for m in memberships if int(m["org_id"]) == org_id), None)
        if not membership:
            raise HTTPException(status_code=403, detail="无权进入该机构")
    elif len(memberships) == 1:
        membership = memberships[0]
    else:
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "message": "请选择机构",
                "orgs": [_membership_brief(m) for m in memberships],
            },
        )
    payload = session_payload(user, membership)
    write_audit(
        action="inst.sso",
        user_id=int(user["id"]),
        username=str(user.get("username") or "") or None,
        role=str(membership.get("role") or ""),
        module="institution",
        method="POST",
        path="/api/inst/auth/sso",
        status_code=200,
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail=f"机构 SSO：{membership.get('name_cn', '')} / {membership.get('role', '')}",
    )
    return {"ok": True, **payload}


@router.post("/api/inst/auth/switch")
def inst_switch(
    body: dict[str, Any],
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """S02：多机构切换（等价于带 org_id 的 SSO）。"""
    return inst_sso(body, request, authorization)
