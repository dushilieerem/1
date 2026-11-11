# -*- coding: utf-8 -*-
"""机构端 AI 后台任务：页面关闭后继续运行，进度与结果落库。

任务只记录状态和结果摘要；研究版本、一页纸、辩论本身仍由各自服务落盘。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable

from psycopg.types.json import Jsonb

from services.core.db import get_conn
from .inst_schema import ensure_inst_business_schema

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="inst-ai")


def _row(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    for key, value in list(out.items()):
        if isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


def recover_interrupted_jobs() -> int:
    """服务启动时把上一次进程遗留的 running 任务标为失败，避免页面永远转圈。"""
    ensure_inst_business_schema()
    with get_conn() as conn:
        result = conn.execute(
            "UPDATE inst_ai_job SET status='failed', error='服务重启，任务中断，请重新生成', "
            "finished_at=NOW(), updated_at=NOW() WHERE status='running'"
        )
    return int(result.rowcount or 0)


def create_job(
    org_id: int,
    case_id: int,
    kind: str,
    *,
    actor_member_id: int | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    ensure_inst_business_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO inst_ai_job (org_id, case_id, kind, status, progress, detail, created_by)
            VALUES (%s,%s,%s,'running',0,%s,%s) RETURNING *
            """,
            (org_id, case_id, kind, detail, actor_member_id),
        ).fetchone()
    return _row(row) or {}


def update_job(
    job_id: int,
    *,
    status: str | None = None,
    progress: int | None = None,
    detail: str | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE inst_ai_job SET
              status=COALESCE(%s,status),
              progress=COALESCE(%s,progress),
              detail=COALESCE(%s,detail),
              result=COALESCE(%s,result),
              error=%s,
              finished_at=CASE WHEN %s IN ('done','failed') THEN NOW() ELSE finished_at END,
              updated_at=NOW()
            WHERE id=%s
            """,
            (status, progress, detail, Jsonb(result) if result is not None else None, error, status, job_id),
        )


def get_job(org_id: int, case_id: int, job_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM inst_ai_job WHERE id=%s AND org_id=%s AND case_id=%s",
            (job_id, org_id, case_id),
        ).fetchone()
    return _row(row)


def latest_job(org_id: int, case_id: int, kind: str | None = None) -> dict[str, Any] | None:
    sql = "SELECT * FROM inst_ai_job WHERE org_id=%s AND case_id=%s"
    params: list[Any] = [org_id, case_id]
    if kind:
        sql += " AND kind=%s"
        params.append(kind)
    sql += " ORDER BY id DESC LIMIT 1"
    with get_conn() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
    return _row(row)


def submit(job_id: int, fn: Callable[[], dict[str, Any] | None]) -> None:
    """把任务交给后台线程；调用方立即返回，浏览器关闭不影响执行。"""

    def _run() -> None:
        try:
            result = fn() or {}
            update_job(job_id, status="done", progress=100, result=result)
        except Exception as exc:  # noqa: BLE001 - 任务失败要落库给页面展示
            update_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}"[:1200])

    _EXECUTOR.submit(_run)
