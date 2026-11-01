# -*- coding: utf-8 -*-
"""组织、套餐、额度与人工账单（P01/P02/P03/P05）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_admin, require_db_user_id
from services.billing import billing_store as store

router = APIRouter(prefix="/api/orgs", tags=["orgs"])
admin_router = APIRouter(prefix="/api/admin/billing", tags=["admin-billing"])


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (LookupError, KeyError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="组织服务异常")


@router.get("/plans")
def plans() -> dict[str, Any]:
    return {"ok": True, "items": store.list_plans()}


@router.get("")
def my_orgs(uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    return {"ok": True, "items": store.list_my_orgs(uid)}


@router.post("")
def create_org(body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {"ok": True, "org": store.create_org(uid, name=str(body.get("name") or ""))}
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/{org_id}")
def get_org(org_id: int, uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {"ok": True, "org": store.get_org(uid, org_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/{org_id}/members")
def add_member(org_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "org": store.add_member(
                org_id,
                uid,
                username=str(body.get("username") or ""),
                role=str(body.get("role") or "member"),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.delete("/{org_id}/members/{user_id}")
def remove_member(org_id: int, user_id: int, uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {"ok": True, "org": store.remove_member(org_id, uid, user_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.put("/{org_id}/plan")
def set_plan(org_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "org": store.set_plan(uid, org_id, plan_code=str(body.get("plan_code") or "")),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/{org_id}/credits")
def credits(org_id: int, uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "balance": store.credits_balance(org_id),
            "items": store.list_credits(uid, org_id),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/{org_id}/billing/requests")
def billing_requests(org_id: int, uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {"ok": True, "items": store.list_billing_requests(uid, org_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/{org_id}/billing/requests")
def create_billing_request(
    org_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "request": store.request_billing(
                uid,
                org_id,
                kind=str(body.get("kind") or "topup"),
                amount_cents=int(body.get("amount_cents") or 0),
                note=str(body.get("note") or ""),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@admin_router.get("/requests")
def admin_requests(status: str | None = None, admin: dict = Depends(require_admin)) -> dict[str, Any]:
    try:
        return {"ok": True, "items": store.admin_list_billing_requests(status=status)}
    except Exception as exc:
        raise _handle(exc) from exc


@admin_router.post("/requests/{request_id}/resolve")
def admin_resolve(
    request_id: int, body: dict[str, Any], admin: dict = Depends(require_admin)
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "request": store.resolve_billing_request(
                request_id,
                status=str(body.get("status") or "approved"),
                admin_id=int(admin["id"]),
                note=str(body.get("note") or ""),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@admin_router.post("/credits")
def admin_grant(body: dict[str, Any], admin: dict = Depends(require_admin)) -> dict[str, Any]:
    try:
        org_id = body.get("org_id")
        user_id = body.get("user_id")
        return {
            "ok": True,
            "entry": store.grant_credits(
                org_id=int(org_id) if org_id else None,
                user_id=int(user_id) if user_id else None,
                delta=int(body.get("delta") or 0),
                reason=str(body.get("reason") or "admin grant"),
                created_by=int(admin["id"]),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc
