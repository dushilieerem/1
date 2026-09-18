# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from services.auth.auth_store import user_from_authorization
from services.factor.user_factor_store import resolve_db_user_id


def _auth_header(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str | None:
    return authorization


def optional_user(
    authorization: str | None = Depends(_auth_header),
) -> dict[str, Any] | None:
    return user_from_authorization(authorization)


def require_user(
    authorization: str | None = Depends(_auth_header),
) -> dict[str, Any]:
    user = user_from_authorization(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_db_user_id(user: dict[str, Any] = Depends(require_user)) -> int:
    try:
        return resolve_db_user_id(user)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_admin(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if str(user.get("role") or "") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def soft_db_user_id(user: dict[str, Any] | None = Depends(optional_user)) -> int | None:
    if not user:
        return None
    try:
        return resolve_db_user_id(user)
    except PermissionError:
        return None


def request_auth_header(request: Request) -> str | None:
    for key in ("authorization", "Authorization", "AUTHORIZATION"):
        val = request.headers.get(key)
        if val:
            return val
    return None
