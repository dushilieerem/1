# -*- coding: utf-8 -*-
"""管理员：系统审计日志查询与清理。"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Query

from app.deps import require_admin
from services.core.audit_log_store import list_audit_logs, purge_audit_logs

router = APIRouter(tags=["admin-logs"])


@router.get("/api/admin/logs")
def admin_list_logs(
    _admin: dict = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    module: str | None = Query(None),
    username: str | None = Query(None),
    action: str | None = Query(None),
    statusCode: int | None = Query(None, alias="statusCode"),
    statusMin: int | None = Query(None, alias="statusMin"),
    statusMax: int | None = Query(None, alias="statusMax"),
    method: str | None = Query(None),
    writeOnly: bool = Query(False, alias="writeOnly"),
    path: str | None = Query(None),
    since: str | None = Query(None),
    until: str | None = Query(None),
) -> dict:
    return list_audit_logs(
        limit=limit,
        offset=offset,
        module=module,
        username=username,
        action=action,
        status_code=statusCode,
        status_min=statusMin,
        status_max=statusMax,
        method=method,
        write_only=writeOnly,
        path_contains=path,
        since=since,
        until=until,
    )


@router.post("/api/admin/logs/purge")
def admin_purge_logs(
    _admin: dict = Depends(require_admin),
    days: int | None = Query(
        None,
        ge=1,
        le=3650,
        description="删除早于 N 天的记录；默认读环境变量 AUDIT_LOG_RETENTION_DAYS",
    ),
) -> dict:
    retain = days
    if retain is None:
        retain = int(os.environ.get("AUDIT_LOG_RETENTION_DAYS", "30") or "30")
    deleted = purge_audit_logs(days=retain)
    return {"ok": True, "days": retain, "deleted": deleted}
