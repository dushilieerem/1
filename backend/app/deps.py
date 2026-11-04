# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from services.auth.auth_store import user_from_authorization
from services.factor.user_factor_store import resolve_db_user_id
from services.institution.inst_store import (
    user_from_inst_authorization,
    user_from_quant_authorization,
)


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


def require_inst_user(
    authorization: str | None = Depends(_auth_header),
) -> dict[str, Any]:
    """机构端会话：必须是 scope=inst 的令牌且成员状态有效。"""
    ctx = user_from_inst_authorization(authorization)
    if not ctx:
        raise HTTPException(status_code=401, detail="机构端未登录或会话已失效")
    return ctx


def require_quant_user(
    authorization: str | None = Depends(_auth_header),
) -> dict[str, Any]:
    """机构量化会话：product=quant，且成员角色在 QUANT_ROLES。"""
    ctx = user_from_quant_authorization(authorization)
    if not ctx:
        raise HTTPException(status_code=401, detail="机构量化端未登录或会话已失效")
    return ctx


def require_quant_researcher(
    ctx: dict[str, Any] = Depends(require_quant_user),
) -> dict[str, Any]:
    """可执行研究/回测/写资产的量化角色；复核角色不能走这些接口。"""
    if not ctx.get("can_write"):
        raise HTTPException(status_code=403, detail="该量化角色只有复核权限")
    return ctx


def require_quant_reviewer(
    ctx: dict[str, Any] = Depends(require_quant_user),
) -> dict[str, Any]:
    """独立量化复核角色；业务路由必须再校验 reviewer 不是候选作者。"""
    if not ctx.get("can_review"):
        raise HTTPException(status_code=403, detail="需要机构量化复核权限")
    return ctx


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
