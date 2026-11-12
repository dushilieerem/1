# -*- coding: utf-8 -*-
"""基金会计/净值/申赎/报送 API（X01–X06）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_db_user_id
from services.fund import fund_store as store

router = APIRouter(prefix="/api/fund", tags=["fund"])


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (KeyError, LookupError)):
        return HTTPException(status_code=404, detail="基金产品不存在")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="基金服务异常")


@router.get("/products")
def products(uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    return {"ok": True, "items": store.list_products(uid)}


@router.post("/products")
def create_product(body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "product": store.create_product(
                uid,
                code=str(body.get("code") or ""),
                name=str(body.get("name") or ""),
                mgmt_fee=float(body.get("mgmt_fee") or 0.015),
                custody_fee=float(body.get("custody_fee") or 0.0025),
                subscription_fee=float(body.get("subscription_fee") or 0.01),
                redemption_fee=float(body.get("redemption_fee") or 0.005),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/products/{product_id}")
def product(product_id: int, uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {"ok": True, "product": store.get_product(uid, product_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/products/{product_id}/capital")
def capital(product_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {"ok": True, "product": store.add_capital(uid, product_id, float(body.get("amount") or 0))}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/products/{product_id}/positions")
def position(product_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "product": store.add_position(
                uid,
                product_id,
                symbol=str(body.get("symbol") or ""),
                qty=float(body.get("qty") or 0),
                cost=float(body.get("cost") or 0),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/products/{product_id}/nav")
def nav(product_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {"ok": True, "nav": store.compute_nav(uid, product_id, as_of=body.get("as_of"))}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/products/{product_id}/subscribe")
def subscribe(product_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "order": store.subscribe(product_id, uid, amount=float(body.get("amount") or 0), as_of=body.get("as_of")),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/products/{product_id}/redeem")
def redeem(product_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "order": store.redeem(product_id, uid, shares=float(body.get("shares") or 0), as_of=body.get("as_of")),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/products/{product_id}/orders")
def orders(product_id: int, uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        store.get_product(uid, product_id)
        return {"ok": True, "items": store.list_orders(product_id)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.post("/products/{product_id}/report")
def report(product_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {"ok": True, **store.build_report(uid, product_id, as_of=body.get("as_of"))}
    except Exception as exc:
        raise _handle(exc) from exc
