# -*- coding: utf-8 -*-
"""后台任务租约回收：worker 崩溃留下的 running 任务应重新排队。"""
from __future__ import annotations

import uuid

from services.core.db import get_conn
from services.core.job_queue import ensure_job_schema, recover_stale

ensure_job_schema()


def test_stale_running_job_is_requeued_only_after_threshold() -> None:
    kind = f"test.recover.{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        stale = conn.execute(
            "INSERT INTO background_jobs (kind,payload,status,locked_at) "
            "VALUES (%s,'{}'::jsonb,'running',NOW() - INTERVAL '2 hours') RETURNING id",
            (kind,),
        ).fetchone()
        fresh = conn.execute(
            "INSERT INTO background_jobs (kind,payload,status,locked_at) "
            "VALUES (%s,'{}'::jsonb,'running',NOW()) RETURNING id",
            (kind,),
        ).fetchone()
    try:
        assert recover_stale(kind, older_than_sec=3600) == 1
        with get_conn() as conn:
            rows = {
                int(r["id"]): dict(r)
                for r in conn.execute(
                    "SELECT id,status,error FROM background_jobs WHERE id IN (%s,%s)",
                    (stale["id"], fresh["id"]),
                ).fetchall()
            }
        assert rows[int(stale["id"])]["status"] == "queued"
        assert "stale recovered" in rows[int(stale["id"])]["error"]
        assert rows[int(fresh["id"])]["status"] == "running"
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM background_jobs WHERE kind=%s", (kind,))
