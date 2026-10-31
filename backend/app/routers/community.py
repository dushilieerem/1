# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ai.errors import AiError
from ai.router import run_task
from app.deps import optional_user, require_user
from services.community.platform_ref_verify import verify_platform_ref
from services.core.env_config import env
from services.community.community_store import (
    add_favorite,
    create_comment,
    create_post,
    create_report,
    delete_post,
    get_post,
    list_comments,
    list_favorites,
    list_hot_posts,
    list_moderation_posts,
    list_my_posts,
    list_notifications,
    list_posts,
    list_reports,
    mark_notifications_read,
    moderate_post,
    ops_summary,
    purge_post,
    remove_favorite,
    resolve_report,
    search_suggestions,
    set_comment_vote,
    set_post_vote,
    unread_notification_count,
    update_post,
)

router = APIRouter(tags=["community"])


@router.get("/api/community/posts")
def community_list_posts(
    section: str | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("views"),
    limit: int = Query(50),
    offset: int = Query(0),
) -> dict:
    try:
        return list_posts(section=section, q=q, sort=sort, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/community/search/suggest")
def community_search_suggest(
    q: str | None = Query(None),
    limit: int = Query(8, ge=1, le=20),
) -> dict:
    return search_suggestions(q, limit=limit)


@router.get("/api/community/hot")
def community_hot(
    limit: int = Query(10),
    section: str | None = Query(None),
) -> dict:
    try:
        return list_hot_posts(limit=limit, section=section)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/community/favorites")
def community_favorites(
    user: dict = Depends(require_user),
    limit: int = Query(50),
    offset: int = Query(0),
) -> dict:
    return list_favorites(int(user["id"]), limit=limit, offset=offset)


@router.get("/api/community/my-posts")
def community_my_posts(
    user: dict = Depends(require_user),
    limit: int = Query(50),
    offset: int = Query(0),
    status: str = Query("published"),
) -> dict:
    try:
        return list_my_posts(
            int(user["id"]),
            status=status,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/community/moderation")
def community_moderation(
    user: dict = Depends(require_user),
    kind: str = Query("hidden"),
    limit: int = Query(50),
    offset: int = Query(0),
) -> dict:
    try:
        return list_moderation_posts(
            author_role=str(user.get("role") or "user"),
            kind=kind,
            limit=limit,
            offset=offset,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/community/reports")
def community_list_reports(
    user: dict = Depends(require_user),
    status: str = Query("open"),
    limit: int = Query(50),
    offset: int = Query(0),
) -> dict:
    try:
        return list_reports(
            author_role=str(user.get("role") or "user"),
            status=status,
            limit=limit,
            offset=offset,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/community/ops/summary")
def community_ops_summary(
    user: dict = Depends(require_user),
    days: int = Query(7),
) -> dict:
    try:
        return ops_summary(
            author_role=str(user.get("role") or "user"),
            days=days,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/community/notifications")
def community_notifications(
    user: dict = Depends(require_user),
    type: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
) -> dict:
    try:
        return list_notifications(
            int(user["id"]), typ=type, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/community/notifications/unread-count")
def community_unread_count(user: dict = Depends(require_user)) -> dict:
    return unread_notification_count(int(user["id"]))


@router.get("/api/community/posts/{post_id}")
def community_get_post(
    post_id: int,
    bump: str = Query("1"),
    viewer: dict | None = Depends(optional_user),
) -> dict:
    bump_raw = (bump or "1").strip().lower()
    bump_view = bump_raw not in {"0", "false", "no"}
    try:
        return get_post(
            post_id,
            bump_view=bump_view,
            viewer_id=int(viewer["id"]) if viewer else None,
            viewer_role=str((viewer or {}).get("role") or "user"),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/community/posts/{post_id}/comments")
def community_list_comments(
    post_id: int,
    limit: int | None = None,
    offset: int = 0,
    viewer: dict | None = Depends(optional_user),
) -> dict:
    try:
        return list_comments(
            post_id,
            viewer_id=int(viewer["id"]) if viewer else None,
            viewer_role=str((viewer or {}).get("role") or "user"),
            limit=limit,
            offset=offset,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/api/community/posts")
def community_create_post(
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        return create_post(
            int(user["id"]),
            title=str(body.get("title") or ""),
            body=str(body.get("body") or ""),
            section=str(body.get("section") or ""),
            code_snippet=(
                str(body["code_snippet"]) if body.get("code_snippet") else None
            ),
            author_role=str(user.get("role") or "user"),
            status=str(body.get("status") or "published"),
            platform_ref=verify_platform_ref(
                int(user["id"]), body.get("platform_ref")
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/community/posts/{post_id}/ai-review")
def community_ai_review(
    post_id: int,
    user: dict = Depends(require_user),
) -> dict:
    """P1-C08：策略帖自动点评/风险提示；可关闭，结果标注 AI 生成。"""
    if (env("COMMUNITY_AI_REVIEW_ENABLED", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        return {"ok": False, "disabled": True, "error": "AI 点评已关闭"}
    try:
        post = get_post(
            post_id,
            bump_view=False,
            viewer_id=int(user["id"]),
            viewer_role=str(user.get("role") or "user"),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    title = str(post.get("title") or "")
    body = str(post.get("body") or "")[:4000]
    code = str(post.get("code_snippet") or "")[:4000]
    messages = [
        {
            "role": "system",
            "content": (
                "你是量化社区的内容审阅助手。对策略分享给出简洁点评："
                "1) 策略思路与适用市场；2) 主要风险与过拟合迹象；3) 缺失的回测信息。"
                "不预测收益、不构成投资建议；中文，200 字以内。"
            ),
        },
        {
            "role": "user",
            "content": f"标题：{title}\n正文：{body}\n代码：\n{code}",
        },
    ]
    try:
        data = run_task("community.review_strategy", messages=messages)
    except AiError as exc:
        raise HTTPException(
            status_code=int(getattr(exc, "http_status", 503) or 503),
            detail=str(exc) or "AI 点评不可用",
        ) from exc
    return {
        "ok": True,
        "ai_generated": True,
        "review": str(data.get("content") or "").strip(),
        "model": data.get("model"),
        "disclaimer": "AI 生成内容，仅供参考，不构成投资建议。",
    }


@router.post("/api/community/reports")
def community_create_report(
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        comment_raw = body.get("comment_id")
        comment_id = None
        if comment_raw is not None and str(comment_raw).strip() != "":
            comment_id = int(comment_raw)
        return create_report(
            int(user["id"]),
            target_type=str(body.get("target_type") or ""),
            post_id=int(body.get("post_id") or 0),
            comment_id=comment_id,
            reason=str(body.get("reason") or ""),
            detail=str(body.get("detail") or ""),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/community/reports/{report_id}/resolve")
def community_resolve_report(
    report_id: int,
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        return resolve_report(
            report_id,
            author_role=str(user.get("role") or "user"),
            resolver_id=int(user["id"]),
            status=str(body.get("status") or "resolved"),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/community/notifications/read")
def community_mark_read(
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        ids_raw = body.get("ids")
        ids = None
        if isinstance(ids_raw, list):
            ids = [int(x) for x in ids_raw]
        return mark_notifications_read(
            int(user["id"]),
            ids=ids,
            typ=body.get("type"),
            all_unread=bool(body.get("all")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/community/comments/{comment_id}/vote")
def community_comment_vote(
    comment_id: int,
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        return set_comment_vote(
            int(user["id"]), comment_id, int(body.get("value", 0))
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/community/posts/{post_id}/comments")
def community_create_comment(
    post_id: int,
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        parent_raw = body.get("parent_id")
        parent_id = None
        if parent_raw is not None and str(parent_raw).strip() != "":
            parent_id = int(parent_raw)
        images = body.get("images")
        if images is not None and not isinstance(images, list):
            raise ValueError("images 格式错误")
        return create_comment(
            post_id,
            int(user["id"]),
            str(body.get("body") or ""),
            parent_id=parent_id,
            images=images,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/api/community/posts/{post_id}/favorite")
def community_add_favorite(
    post_id: int,
    user: dict = Depends(require_user),
) -> dict:
    try:
        return add_favorite(int(user["id"]), post_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/api/community/posts/{post_id}/vote")
def community_post_vote(
    post_id: int,
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        return set_post_vote(int(user["id"]), post_id, int(body.get("value", 0)))
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/api/community/posts/{post_id}/moderate")
def community_moderate(
    post_id: int,
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        pinned = body.get("pinned")
        status = body.get("status")
        return moderate_post(
            post_id,
            author_role=str(user.get("role") or "user"),
            pinned=None if pinned is None else bool(pinned),
            status=None if status is None else str(status),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/api/community/posts/{post_id}/purge")
def community_purge(
    post_id: int,
    user: dict = Depends(require_user),
) -> dict:
    try:
        return purge_post(
            post_id,
            author_role=str(user.get("role") or "user"),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/api/community/posts/{post_id}")
def community_update_post(
    post_id: int,
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        return update_post(
            int(user["id"]),
            post_id,
            title=str(body.get("title") or ""),
            body=str(body.get("body") or ""),
            section=str(body.get("section") or ""),
            code_snippet=(
                str(body["code_snippet"]) if body.get("code_snippet") else None
            ),
            author_role=str(user.get("role") or "user"),
            status=(str(body["status"]) if body.get("status") is not None else None),
            platform_ref=verify_platform_ref(
                int(user["id"]), body.get("platform_ref")
            ),
            clear_platform_ref=bool(body.get("clear_platform_ref")),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/community/posts/{post_id}/favorite")
def community_remove_favorite(
    post_id: int,
    user: dict = Depends(require_user),
) -> dict:
    return remove_favorite(int(user["id"]), post_id)


@router.delete("/api/community/posts/{post_id}")
def community_delete_post(
    post_id: int,
    user: dict = Depends(require_user),
) -> dict:
    try:
        return delete_post(
            int(user["id"]),
            post_id,
            author_role=str(user.get("role") or "user"),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
