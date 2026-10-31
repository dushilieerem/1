# -*- coding: utf-8 -*-
"""管理员：用户管理（列表/禁用/角色/重置密码）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from app.deps import require_admin
from services.admin import user_admin_store as store
from services.core.audit_log_store import write_audit

router = APIRouter(tags=["admin-users"])


def _ip(request: Request) -> str | None:
    xf = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xf:
        return xf.split(",")[0].strip() or None
    return request.client.host if request.client else None


def _audit(request: Request, admin: dict[str, Any], action: str, detail: str, user_id: int | None = None) -> None:
    write_audit(
        action=action,
        user_id=int(admin["id"]),
        username=str(admin.get("username") or ""),
        role=str(admin.get("role") or "admin"),
        module="admin",
        method="POST",
        path=str(request.url.path),
        status_code=200,
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail=detail[:300],
    )


@router.get("/api/admin/users")
def users(
    q: str | None = Query(None),
    status: str | None = Query(None),
    role: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    return {"ok": True, **store.list_users(q=q, status=status, role=role, limit=limit, offset=offset)}


@router.post("/api/admin/users/{user_id}/status")
def set_status(
    user_id: int,
    request: Request,
    body: dict[str, Any] = Body(...),
    admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    status = str(body.get("status") or "")
    if int(user_id) == int(admin["id"]) and status != "active":
        raise HTTPException(status_code=400, detail="不能禁用当前管理员账号")
    try:
        user = store.set_status(user_id, status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(request, admin, "admin.user.status", f"user={user_id} status={status}", user_id)
    return {"ok": True, "user": user}


@router.post("/api/admin/users/{user_id}/role")
def set_role(
    user_id: int,
    request: Request,
    body: dict[str, Any] = Body(...),
    admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    role = str(body.get("role") or "")
    if int(user_id) == int(admin["id"]) and role != "admin":
        raise HTTPException(status_code=400, detail="不能降级当前管理员账号")
    try:
        user = store.set_role(user_id, role)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(request, admin, "admin.user.role", f"user={user_id} role={role}", user_id)
    return {"ok": True, "user": user}


@router.post("/api/admin/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    request: Request,
    body: dict[str, Any] = Body(...),
    admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    try:
        out = store.reset_password(user_id, str(body.get("password") or ""))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(request, admin, "admin.user.reset_password", f"user={user_id}", user_id)
    return {"ok": True, **out}
