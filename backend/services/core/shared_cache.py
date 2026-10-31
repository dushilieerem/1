# -*- coding: utf-8 -*-
"""跨实例共享缓存（P1-O06）。

小体量 JSON 值（目录、健康摘要、指标快照）可放 PostgreSQL，避免各实例重复计算。
不适合大对象；过期由读写时惰性清理。
"""
from __future__ import annotations

import json
from typing import Any

from services.core.db import get_conn


def ensure_cache_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shared_cache (
              key        TEXT PRIMARY KEY,
              value      JSONB NOT NULL,
              expires_at TIMESTAMPTZ,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def get(key: str) -> Any | None:
    ensure_cache_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT value FROM shared_cache
            WHERE key = %s AND (expires_at IS NULL OR expires_at > NOW())
            """,
            (str(key),),
        ).fetchone()
    return row["value"] if row else None


def set(key: str, value: Any, *, ttl_sec: int = 300) -> None:
    ensure_cache_schema()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO shared_cache (key, value, expires_at, updated_at)
            VALUES (%s, %s::jsonb,
                    CASE WHEN %s > 0 THEN NOW() + make_interval(secs => %s) ELSE NULL END,
                    NOW())
            ON CONFLICT (key) DO UPDATE SET
              value = EXCLUDED.value,
              expires_at = EXCLUDED.expires_at,
              updated_at = NOW()
            """,
            (str(key), json.dumps(value, ensure_ascii=False), int(ttl_sec), int(ttl_sec)),
        )


def delete(key: str) -> None:
    ensure_cache_schema()
    with get_conn() as conn:
        conn.execute("DELETE FROM shared_cache WHERE key = %s", (str(key),))


def purge_expired() -> int:
    ensure_cache_schema()
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM shared_cache WHERE expires_at IS NOT NULL AND expires_at <= NOW()"
        )
        return int(cur.rowcount or 0)
