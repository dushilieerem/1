# -*- coding: utf-8 -*-
"""客服工单（H14）：用户端与管理员端。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.deps import require_admin, require_db_user_id
from services.core.rate_limit import enforce_rate_limit
from services.support import support_store as store

router = APIRouter(prefix="/api/support", tags=["support"])
admin_router = APIRouter(prefix="/api/admin/support", tags=["admin-support"])


def _limit(request: Request, scope: str, limit: int) -> None:
    enforce_rate_limit(request, scope=scope, limit=limit, window_sec=60)


@router.get("/tickets")
def my_tickets(
    limit: int = 20,
    offset: int = 0,
    uid: int = Depends(require_db_user_id),
) -> dict[str, Any]:
    return {"ok": True, **store.list_my_tickets(uid, limit=limit, offset=offset)}


@router.post("/tickets")
def create_ticket(
    body: dict[str, Any],
    request: Request,
    uid: int = Depends(require_db_user_id),
) -> dict[str, Any]:
    _limit(request, "support.create", 10)
    try:
        ticket = store.create_ticket(
            uid,
            category=str(body.get("category") or "other"),
            subject=str(body.get("subject") or ""),
            body=str(body.get("body") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "ticket": ticket}


@router.get("/tickets/{ticket_id}")
def my_ticket(ticket_id: int, uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {"ok": True, "ticket": store.get_my_ticket(uid, ticket_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="工单不存在") from None


@router.post("/tickets/{ticket_id}/replies")
def reply_ticket(
    ticket_id: int,
    body: dict[str, Any],
    request: Request,
    uid: int = Depends(require_db_user_id),
) -> dict[str, Any]:
    _limit(request, "support.reply", 30)
    try:
        ticket = store.add_user_reply(uid, ticket_id, str(body.get("body") or ""))
    except KeyError:
        raise HTTPException(status_code=404, detail="工单不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "ticket": ticket}


@admin_router.get("/tickets")
def admin_tickets(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return {"ok": True, **store.admin_list_tickets(status=status, limit=limit, offset=offset)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_router.get("/tickets/{ticket_id}")
def admin_ticket(ticket_id: int, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        return {"ok": True, "ticket": store.admin_get_ticket(ticket_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="工单不存在") from None


@admin_router.post("/tickets/{ticket_id}/replies")
def admin_reply(
    ticket_id: int,
    body: dict[str, Any],
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    try:
        ticket = store.admin_reply(
            int(admin["id"]),
            ticket_id,
            str(body.get("body") or ""),
            status=str(body["status"]) if body.get("status") else None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="工单不存在") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "ticket": ticket}
