# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_db_user_id, require_user
from services.factor.detect_store import (
    create_project,
    delete_project,
    delete_run,
    get_project,
    get_run,
    list_all_runs,
    list_projects,
    list_runs,
    save_run,
    update_run_flagged,
    update_run_remark,
    upsert_project,
)

router = APIRouter(tags=["detect"])


@router.get("/api/detect/projects")
def detect_list_projects(
    visible: str = Query("0"),
    uid: int = Depends(require_db_user_id),
) -> dict:
    visible_only = visible not in {"0", "false", "no"}
    return list_projects(uid, visible_only=visible_only)


@router.post("/api/detect/projects")
def detect_create_or_upsert(
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        if body.get("factorName") is not None or body.get("factor_name") is not None:
            if not body.get("id") and not body.get("config"):
                return create_project(
                    uid,
                    factor_name=str(
                        body.get("factorName") or body.get("factor_name") or "custom_combo"
                    ),
                    description=str(body.get("description") or body.get("name") or ""),
                    display_name=(str(body["name"]) if body.get("name") else None),
                )
        return upsert_project(uid, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/detect/projects/{project_id}/runs")
def detect_list_runs(
    project_id: str,
    uid: int = Depends(require_db_user_id),
) -> dict:
    return list_runs(uid, project_id)


@router.get("/api/detect/projects/{project_id}")
def detect_get_project(
    project_id: str,
    uid: int = Depends(require_db_user_id),
) -> dict:
    if "/" in project_id:
        raise HTTPException(status_code=404, detail="not found")
    try:
        return get_project(uid, project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.put("/api/detect/projects/{project_id}")
def detect_put_project(
    project_id: str,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:return upsert_project(uid, {**body, "id": project_id})
    except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc


@router.delete("/api/detect/projects/{project_id}")
def detect_delete_project(
    project_id: str,
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return delete_project(uid, project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/api/detect/runs")
def detect_save_run(
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return save_run(uid, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/detect/runs")
def detect_list_all_runs(uid: int = Depends(require_db_user_id)) -> dict:
    return list_all_runs(uid)


@router.patch("/api/detect/runs/{run_id}")
def detect_patch_run(
    run_id: str,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    has_remark = "remark" in body
    has_flagged = "flagged" in body
    if not has_remark and not has_flagged:
        raise HTTPException(status_code=400, detail="缺少 remark 或 flagged")
    try:
        if has_flagged:
            return update_run_flagged(uid, run_id, bool(body.get("flagged")))
        return update_run_remark(uid, run_id, str(body.get("remark") or ""))
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/detect/runs/{run_id}")
def detect_get_run(
    run_id: str,
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return get_run(uid, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.delete("/api/detect/runs/{run_id}")
def detect_delete_run(
    run_id: str,
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return delete_run(uid, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
