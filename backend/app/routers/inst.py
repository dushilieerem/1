# -*- coding: utf-8 -*-
"""机构端接口：独立登录、机构会话与工作区权限。

路径前缀 `/api/inst/*` 只接受机构令牌（scope=inst）；
个人版 `/api/auth/*` 令牌不能访问这里。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.deps import require_inst_user
from services.core.audit_log_store import write_audit
from services.core.env_config import env
from services.core.rate_limit import enforce_rate_limit
from services.institution.inst_store import login_inst, login_payload, me_payload

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
