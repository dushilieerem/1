# -*- coding: utf-8 -*-
"""因子试算记录（P1-F07）：服务端持久化，可追溯、可复用、可清理。

浏览器刷新/换机后仍能看到历史；记录按用户隔离。
"""
from __future__ import annotations

import json
from typing import Any

from services.core.db import get_conn


def ensure_trial_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factor_trial_records (
              id           BIGSERIAL PRIMARY KEY,
              user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              factor_name  TEXT NOT NULL,
              body         TEXT NOT NULL,
              universe     TEXT,
              period       TEXT,
              ok           BOOLEAN NOT NULL,
              metrics      JSONB,
              stats        JSONB,
              error        TEXT,
              elapsed_ms   INT,
              created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_factor_trial_records_user "
            "ON factor_trial_records (user_id, created_at DESC)"
        )


def save_trial(
    *,
    user_id: int,
    factor_name: str,
    body: str,
    universe: str,
    period: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    elapsed_ms: int | None = None,
) -> dict[str, Any]:
    """保存一次试算（成功或失败都留痕）。"""
    ensure_trial_schema()
    ok = result is not None
    metrics = (result or {}).get("metrics") if result else None
    stats = (result or {}).get("stats") if result else None
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO factor_trial_records (
              user_id, factor_name, body, universe, period, ok, metrics, stats, error, elapsed_ms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            RETURNING id, created_at
            """,
            (
                int(user_id),
                factor_name,
                body,
                universe,
                period,
                ok,
                json.dumps(metrics, ensure_ascii=False) if metrics is not None else None,
                json.dumps(stats, ensure_ascii=False) if stats is not None else None,
                error,
                elapsed_ms,
            ),
        ).fetchone()
    return {"id": int(row["id"]), "created_at": row["created_at"].isoformat()}


def list_trials(user_id: int, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    ensure_trial_schema()
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total_row = conn.execute(
            "SELECT COUNT(*) AS n FROM factor_trial_records WHERE user_id = %s",
            (int(user_id),),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT id, factor_name, body, universe, period, ok, metrics, stats,
                   error, elapsed_ms, created_at
            FROM factor_trial_records
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (int(user_id), limit, offset),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["created_at"] = row["created_at"].isoformat()
        items.append(item)
    return {"items": items, "total": int(total_row["n"] or 0), "limit": limit, "offset": offset}


def get_trial(user_id: int, trial_id: int) -> dict[str, Any] | None:
    ensure_trial_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, factor_name, body, universe, period, ok, metrics, stats,
                   error, elapsed_ms, created_at
            FROM factor_trial_records
            WHERE id = %s AND user_id = %s
            """,
            (int(trial_id), int(user_id)),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["created_at"] = row["created_at"].isoformat()
    return item


def delete_trial(user_id: int, trial_id: int) -> bool:
    ensure_trial_schema()
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM factor_trial_records WHERE id = %s AND user_id = %s",
            (int(trial_id), int(user_id)),
        )
        return cur.rowcount > 0
