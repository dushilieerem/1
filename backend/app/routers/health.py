# -*- coding: utf-8 -*-
from __future__ import annotations

import os

from fastapi import APIRouter

from app.bootstrap import FACTOR_DIR
from services.core.db import get_conn, pool_stats
from services.core.env_config import env

router = APIRouter(tags=["health"])

PORT = int(os.environ.get("SVQUANT_BACKEND_PORT", "8766"))


@router.get("/api/health")
def health() -> dict:
    db_ok = False
    schema: dict | None = None
    data_sync: dict | None = None
    queue: dict | None = None
    connections: dict | None = None
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
            exists = conn.execute(
                "SELECT to_regclass('public.data_sync_state') AS t"
            ).fetchone()
            if exists and exists.get("t"):
                row = conn.execute(
                    "SELECT view_id, data_date, status, finished_at, last_error "
                    "FROM data_sync_state WHERE id=1"
                ).fetchone()
                if row:
                    data_sync = {
                        "view_id": row.get("view_id"),
                        "data_date": str(row.get("data_date") or "") or None,
                        "status": row.get("status"),
                        "finished_at": str(row.get("finished_at") or "") or None,
                        "last_error": row.get("last_error"),
                    }
            q_exists = conn.execute(
                "SELECT to_regclass('public.background_jobs') AS t"
            ).fetchone()
            if q_exists and q_exists.get("t"):
                rows = conn.execute(
                    "SELECT status, COUNT(*) AS n FROM background_jobs GROUP BY status"
                ).fetchall()
                queue = {str(r["status"]): int(r["n"] or 0) for r in rows}
            conn_row = conn.execute(
                "SELECT COUNT(*) AS used, current_setting('max_connections') AS max_conn "
                "FROM pg_stat_activity"
            ).fetchone()
            if conn_row:
                connections = {
                    "used": int(conn_row.get("used") or 0),
                    "limit": int(conn_row.get("max_conn") or 0),
                }
        db_ok = True
        from services.core.migrations import status as migration_status

        schema = migration_status()
    except Exception:
        db_ok = False
    return {
        "ok": db_ok,
        "service": "svquant",
        "port": PORT,
        "db": "ok" if db_ok else "error",
        "db_pool": pool_stats(),
        "schema": schema,
        "data_sync": data_sync,
        "queue": queue,
        "db_connections": connections,
        "worker_mode": (env("SVQUANT_WORKER_MODE", "single") or "single"),
        "multi_instance_supported": False,
        "in_memory_state": [
            "rate_limit",
            "market_cache",
            "factor_backtest_queue",
            "kh_progress",
            "audit_dedupe",
        ],
        "factor_dir": str(FACTOR_DIR),
        "note": "single-worker deployment; shared state requires Redis/queue (D-06)",
    }
