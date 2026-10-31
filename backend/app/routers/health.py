# -*- coding: utf-8 -*-
from __future__ import annotations

import os

from fastapi import APIRouter

from app.bootstrap import FACTOR_DIR
from services.core.db import get_conn
from services.core.env_config import env

router = APIRouter(tags=["health"])

PORT = int(os.environ.get("SVQUANT_BACKEND_PORT", "8766"))


@router.get("/api/health")
def health() -> dict:
    db_ok = False
    schema: dict | None = None
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
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
        "schema": schema,
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
