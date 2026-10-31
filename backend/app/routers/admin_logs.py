# -*- coding: utf-8 -*-
"""管理员：系统审计日志查询与清理。"""
from __future__ import annotations

import csv
import io
import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

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

@router.get("/api/admin/logs/export")
def admin_export_logs(
    _admin: dict = Depends(require_admin),
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
    maxRows: int = Query(5000, ge=1, le=20000),
) -> Response:
    """按筛选导出审计 CSV（服务端分页拉取，最多 maxRows）。"""
    items: list[dict] = []
    offset = 0
    while len(items) < maxRows:
        page = list_audit_logs(
            limit=min(200, maxRows - len(items)),
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
        batch = page.get("items") or []
        items.extend(batch)
        offset += len(batch)
        if not batch or offset >= int(page.get("total") or 0):
            break
    fields = ["id", "createdAt", "username", "role", "action", "module", "method", "path", "statusCode", "ip", "detail"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow({k: item.get(k) for k in fields})
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="svquant-audit.csv"'},
    )

