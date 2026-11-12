# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.deps import optional_user, require_user
from services.auth.auth_store import login_user, me_response, register_user, revoke_user_tokens, user_from_authorization
from services.auth.profile_store import (
    follow_user,
    get_public_profile,
    list_user_follows,
    list_user_posts,
    unfollow_user,
    update_my_profile,
)
from services.core.audit_log_store import write_audit
from services.core.env_config import env
from services.core.rate_limit import enforce_rate_limit


def _ip(request: Request) -> str | None:
    xf = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xf:
        return xf.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def _rate_limit_int(key: str, default: int) -> int:
    try:
        return max(1, int(env(key, str(default)) or default))
    except (TypeError, ValueError):
        return default


def _enforce_auth_rate_limit(request: Request, *, scope: str, limit: int) -> None:
    enforce_rate_limit(request, scope=scope, limit=limit, window_sec=60)


router = APIRouter(tags=["auth"])


@router.post("/api/auth/forgot-password")
def auth_forgot_password(body: dict[str, Any], request: Request) -> dict:
    _enforce_auth_rate_limit(request, scope="auth.forgot", limit=_rate_limit_int("AUTH_FORGOT_RATE_LIMIT", 5))
    identifier = str(body.get("identifier") or body.get("email") or body.get("username") or "").strip()
    from services.auth.password_reset_store import request_reset

    token = request_reset(identifier)
    write_audit(
        action="auth.forgot_password",
        username=identifier or None,
        role="user",
        module="auth",
        method="POST",
        path="/api/auth/forgot-password",
        status_code=200,
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail="已受理找回密码请求",
    )
    out: dict[str, Any] = {"ok": True, "message": "如果账号存在，重置方式将发送到绑定邮箱或由管理员处理。"}
    if token and (env("AUTH_RESET_DEBUG", "0") or "0").strip() in {"1", "true", "True"}:
        out["reset_token"] = token
    return out


@router.post("/api/auth/reset-password")
def auth_reset_password(body: dict[str, Any], request: Request) -> dict:
    from services.auth.password_reset_store import reset_password

    try:
        reset_password(str(body.get("token") or ""), str(body.get("password") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_audit(
        action="auth.reset_password",
        module="auth",
        method="POST",
        path="/api/auth/reset-password",
        status_code=200,
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail="密码已重置",
    )
    return {"ok": True}


@router.post("/api/auth/sso")
def auth_sso(body: dict[str, Any], request: Request) -> dict:
    """主站令牌换 H5 会话：校验现有 JWT，返回同一用户与令牌。"""
    token = str(body.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="缺少 token")
    user = user_from_authorization(f"Bearer {token}")
    if not user:
        raise HTTPException(status_code=401, detail="token 无效或用户已禁用")
    write_audit(
        action="auth.sso",
        user_id=int(user["id"]) if user.get("id") else None,
        username=str(user.get("username") or ""),
        role=str(user.get("role") or "user"),
        module="auth",
        method="POST",
        path="/api/auth/sso",
        status_code=200,
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail="主站令牌换 H5 会话",
    )
    return {"ok": True, "user": user, "token": token, "mode": "svquant"}


@router.post("/api/auth/register")
def auth_register(body: dict[str, Any], request: Request) -> dict:
    _enforce_auth_rate_limit(
        request,
        scope="auth.register",
        limit=_rate_limit_int("AUTH_REGISTER_RATE_LIMIT", 10),
    )
    from services.core.public_switches import registration_open

    if not registration_open():
        raise HTTPException(status_code=403, detail="注册暂未开放，请通过邀请或等待公测")
    username = str(body.get("username") or "")
    try:
        out = register_user(
            username=username,
            password=str(body.get("password") or ""),
            email=(str(body["email"]) if body.get("email") else None),
            display_name=(str(body["display_name"]) if body.get("display_name") else None),
        )
        user = out.get("user") if isinstance(out, dict) else None
        write_audit(
            action="auth.register",
            user_id=int(user["id"]) if isinstance(user, dict) and user.get("id") else None,
            username=str(user.get("username") or username) if isinstance(user, dict) else username,
            role=str(user.get("role") or "user") if isinstance(user, dict) else "user",
            module="auth",
            method="POST",
            path="/api/auth/register",
            resource="/api/auth/register",
            status_code=200,
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail="注册成功",
        )
        return out
    except ValueError as exc:
        write_audit(
            action="auth.register_failed",
            username=username or None,
            module="auth",
            method="POST",
            path="/api/auth/register",
            resource="/api/auth/register",
            status_code=400,
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail=str(exc)[:200],
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/auth/login")
def auth_login(body: dict[str, Any], request: Request) -> dict:
    _enforce_auth_rate_limit(
        request,
        scope="auth.login",
        limit=_rate_limit_int("AUTH_LOGIN_RATE_LIMIT", 30),
    )
    username = str(body.get("username") or "")
    try:
        out = login_user(
            username=username,
            password=str(body.get("password") or ""),
        )
        user = out.get("user") if isinstance(out, dict) else None
        write_audit(
            action="auth.login",
            user_id=int(user["id"]) if isinstance(user, dict) and user.get("id") else None,
            username=str(user.get("username") or username) if isinstance(user, dict) else username,
            role=str(user.get("role") or "") if isinstance(user, dict) else None,
            module="auth",
            method="POST",
            path="/api/auth/login",
            resource="/api/auth/login",
            status_code=200,
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail="登录成功",
        )
        return out
    except ValueError as exc:
        write_audit(
            action="auth.login_failed",
            username=username or None,
            module="auth",
            method="POST",
            path="/api/auth/login",
            resource="/api/auth/login",
            status_code=401,
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail="登录失败",
        )
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/api/auth/account/delete")
def auth_delete_account(
    body: dict[str, Any], request: Request, user: dict = Depends(require_user)
) -> dict:
    """账号注销：校验密码 + 确认词，删除个人数据并匿名化账号。"""
    _enforce_auth_rate_limit(
        request, scope="auth.account_delete", limit=_rate_limit_int("AUTH_DELETE_RATE_LIMIT", 3)
    )
    from services.auth.account_store import delete_account

    try:
        out = delete_account(
            int(user["id"]),
            password=str(body.get("password") or ""),
            confirm=str(body.get("confirm") or ""),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_audit(
        action="auth.account_delete",
        user_id=int(user["id"]),
        username=str(out.get("username") or ""),
        role=str(user.get("role") or "user"),
        module="auth",
        method="POST",
        path="/api/auth/account/delete",
        status_code=200,
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail=f"账号已注销，清理 {sum(out.get('purged', {}).values())} 行个人数据",
    )
    return out


@router.post("/api/auth/logout")
def auth_logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """吊销当前用户全部令牌（token_version +1）。无令牌也返回成功。"""
    user = user_from_authorization(authorization)
    if user and int(user.get("id") or 0) > 0:
        revoke_user_tokens(int(user["id"]))
    return {"ok": True}


@router.get("/api/auth/me")
def auth_me(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    try:
        return me_response(authorization)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/api/profile/me")
def profile_me(body: dict[str, Any], user: dict = Depends(require_user)) -> dict:
    kwargs: dict = {}
    for k in ("display_name", "headline", "bio", "avatar_url", "cover_url"):
        if k in body:
            kwargs[k] = body.get(k)
    try:
        return update_my_profile(int(user["id"]), **kwargs)
    except KeyError:
        raise HTTPException(status_code=404, detail="用户不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/users/{username}/posts")
def user_posts(
    username: str,
    limit: int = Query(20),
    offset: int = Query(0),
    section: str | None = Query(None),
) -> dict:
    try:
        return list_user_posts(username, limit=limit, offset=offset, section=section)
    except KeyError:
        raise HTTPException(status_code=404, detail="用户不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/users/{username}/following")
def user_following(
    username: str,
    limit: int = Query(30),
    offset: int = Query(0),
    viewer: dict | None = Depends(optional_user),
) -> dict:
    try:
        return list_user_follows(
            username,
            kind="following",
            viewer_id=int(viewer["id"]) if viewer else None,
            limit=limit,
            offset=offset,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="用户不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/users/{username}/followers")
def user_followers(
    username: str,
    limit: int = Query(30),
    offset: int = Query(0),
    viewer: dict | None = Depends(optional_user),
) -> dict:
    try:
        return list_user_follows(
            username,
            kind="followers",
            viewer_id=int(viewer["id"]) if viewer else None,
            limit=limit,
            offset=offset,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="用户不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/users/{username}/follow")
def user_follow(username: str, user: dict = Depends(require_user)) -> dict:
    try:
        return follow_user(int(user["id"]), username)
    except KeyError:
        raise HTTPException(status_code=404, detail="用户不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/users/{username}/follow")
def user_unfollow(username: str, user: dict = Depends(require_user)) -> dict:
    try:
        return unfollow_user(int(user["id"]), username)
    except KeyError:
        raise HTTPException(status_code=404, detail="用户不存在") from None


@router.get("/api/users/{username}")
def user_profile(
    username: str,
    viewer: dict | None = Depends(optional_user),
) -> dict:
    if "/" in username or not username:
        raise HTTPException(status_code=404, detail="not found")
    try:
        return get_public_profile(
            username, viewer_id=int(viewer["id"]) if viewer else None
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="用户不存在") from None
