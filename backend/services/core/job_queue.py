# -*- coding: utf-8 -*-
"""跨实例后台任务队列（P1-O06）。

PostgreSQL `SKIP LOCKED` 抢占：任意 worker 实例都能处理任务，不需要 Redis/Celery。
用法：
    enqueue("news.ingest", {"limit": 12})
    start_worker("news.ingest", handler)   # 每个实例启动一个
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

from services.core.db import get_conn

_lock = threading.Lock()
_workers: dict[str, threading.Thread] = {}
_started = False


def ensure_job_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS background_jobs (
              id          BIGSERIAL PRIMARY KEY,
              kind        TEXT NOT NULL,
              payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
              status      TEXT NOT NULL DEFAULT 'queued',
              attempts    INT NOT NULL DEFAULT 0,
              error       TEXT,
              locked_at   TIMESTAMPTZ,
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_background_jobs_claim "
            "ON background_jobs (kind, status, id)"
        )


def enqueue(kind: str, payload: dict[str, Any] | None = None) -> int:
    ensure_job_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO background_jobs (kind, payload)
            VALUES (%s, %s::jsonb) RETURNING id
            """,
            (str(kind), json.dumps(payload or {}, ensure_ascii=False)),
        ).fetchone()
    return int(row["id"])


def claim(kind: str) -> dict[str, Any] | None:
    """原子领取一个任务；多实例并发安全。"""
    ensure_job_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE background_jobs
            SET status = 'running', attempts = attempts + 1,
                locked_at = NOW(), updated_at = NOW()
            WHERE id = (
              SELECT id FROM background_jobs
              WHERE kind = %s AND status = 'queued'
              ORDER BY id
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            RETURNING *
            """,
            (str(kind),),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["payload"] = item.get("payload") or {}
    return item


def complete(job_id: int, result: dict[str, Any] | None = None) -> None:
    ensure_job_schema()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE background_jobs
            SET status = 'done', error = NULL, updated_at = NOW(),
                payload = payload || %s::jsonb
            WHERE id = %s
            """,
            (json.dumps({"result": result or {}}, ensure_ascii=False), int(job_id)),
        )


def fail(job_id: int, error: str) -> None:
    ensure_job_schema()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE background_jobs
            SET status = 'failed', error = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (str(error)[:1000], int(job_id)),
        )


def job_status(job_id: int) -> dict[str, Any] | None:
    ensure_job_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM background_jobs WHERE id = %s", (int(job_id),)
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["created_at"] = row["created_at"].isoformat()
    item["updated_at"] = row["updated_at"].isoformat()
    return item


def start_worker(
    kind: str,
    handler: Callable[[dict[str, Any]], dict[str, Any] | None],
    *,
    poll_sec: float = 5.0,
) -> None:
    """每个实例启动一个轮询 worker（幂等）。"""
    global _started
    with _lock:
        if kind in _workers and _workers[kind].is_alive():
            return

        def _loop() -> None:
            while True:
                job = None
                try:
                    job = claim(kind)
                except Exception:
                    job = None
                if not job:
                    time.sleep(poll_sec)
                    continue
                try:
                    result = handler(job.get("payload") or {})
                    complete(int(job["id"]), result if isinstance(result, dict) else None)
                except Exception as exc:  # noqa: BLE001
                    fail(int(job["id"]), str(exc))

        thread = threading.Thread(target=_loop, name=f"job-worker-{kind}", daemon=True)
        thread.start()
        _workers[kind] = thread
        _started = True
