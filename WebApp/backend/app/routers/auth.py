# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.deps import optional_user, require_user
from services.auth.auth_store import login_user, me_response, register_user
from services.auth.profile_store import (
    follow_user,
    get_public_profile,
    list_user_follows,
    list_user_posts,
    unfollow_user,
    update_my_profile,
)

router = APIRouter(tags=["auth"])


@router.post("/api/auth/register")
def auth_register(body: dict[str, Any]) -> dict:
    try:
        return register_user(
            username=str(body.get("username") or ""),
            password=str(body.get("password") or ""),
            email=(str(body["email"]) if body.get("email") else None),
            display_name=(str(body["display_name"]) if body.get("display_name") else None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/auth/login")
def auth_login(body: dict[str, Any]) -> dict:
    try:
        return login_user(
            username=str(body.get("username") or ""),
            password=str(body.get("password") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


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
