# -*- coding: utf-8 -*-
"""用户研究资产 CRUD（FEAT-018）：静态证券池与固定权重组合基准。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_db_user_id
from services.research import asset_store as store

router = APIRouter(prefix="/api/research/assets", tags=["research-assets"])


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail="资产不存在")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="研究资产服务异常")


@router.get("/universes")
def list_universes(uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    return {"ok": True, "items": store.list_universes(uid)}


@router.post("/universes")
def create_universe(body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "asset": store.create_universe(
                uid,
                name=str(body.get("name") or ""),
                symbols=body.get("symbols") or [],
                description=str(body.get("description") or ""),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/universes/{asset_id}")
def get_universe(
    asset_id: int, version: int | None = None, uid: int = Depends(require_db_user_id)
) -> dict[str, Any]:
    try:
        return {"ok": True, "asset": store.get_universe(uid, asset_id, version=version)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.put("/universes/{asset_id}")
def update_universe(
    asset_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "asset": store.update_universe(
                uid,
                asset_id,
                name=body.get("name"),
                description=body.get("description"),
                symbols=body.get("symbols"),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.delete("/universes/{asset_id}")
def delete_universe(asset_id: int, uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        store.delete_universe(uid, asset_id)
    except Exception as exc:
        raise _handle(exc) from exc
    return {"ok": True}


@router.get("/universes/{asset_id}/snapshot")
def universe_snapshot(
    asset_id: int, version: int | None = None, uid: int = Depends(require_db_user_id)
) -> dict[str, Any]:
    try:
        return {"ok": True, "snapshot": store.resolve_universe_snapshot(uid, asset_id, version=version)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/benchmarks")
def list_benchmarks(uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    return {"ok": True, "items": store.list_benchmarks(uid)}


@router.post("/benchmarks")
def create_benchmark(body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "asset": store.create_benchmark(
                uid,
                name=str(body.get("name") or ""),
                weights=body.get("weights") or [],
                description=str(body.get("description") or ""),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.get("/benchmarks/{asset_id}")
def get_benchmark(
    asset_id: int, version: int | None = None, uid: int = Depends(require_db_user_id)
) -> dict[str, Any]:
    try:
        return {"ok": True, "asset": store.get_benchmark(uid, asset_id, version=version)}
    except Exception as exc:
        raise _handle(exc) from exc


@router.put("/benchmarks/{asset_id}")
def update_benchmark(
    asset_id: int, body: dict[str, Any], uid: int = Depends(require_db_user_id)
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "asset": store.update_benchmark(
                uid,
                asset_id,
                name=body.get("name"),
                description=body.get("description"),
                weights=body.get("weights"),
            ),
        }
    except Exception as exc:
        raise _handle(exc) from exc


@router.delete("/benchmarks/{asset_id}")
def delete_benchmark(asset_id: int, uid: int = Depends(require_db_user_id)) -> dict[str, Any]:
    try:
        store.delete_benchmark(uid, asset_id)
    except Exception as exc:
        raise _handle(exc) from exc
    return {"ok": True}


@router.get("/benchmarks/{asset_id}/snapshot")
def benchmark_snapshot(
    asset_id: int, version: int | None = None, uid: int = Depends(require_db_user_id)
) -> dict[str, Any]:
    try:
        return {"ok": True, "snapshot": store.resolve_benchmark_snapshot(uid, asset_id, version=version)}
    except Exception as exc:
        raise _handle(exc) from exc
