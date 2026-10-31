# -*- coding: utf-8 -*-
"""AI 研究链跨设备状态（P1-F07/A01 的草稿部分）。

idea → draft → report 三段快照按用户保存，浏览器 sessionStorage 仍作缓存；
服务端用于换机/换浏览器后恢复最近一次研究链。
"""
from __future__ import annotations

import json
from typing import Any

from services.core.db import get_conn

_KEYS = ("idea", "draft", "report")


def ensure_chain_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_chain_state (
              user_id    BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
              idea       JSONB,
              draft      JSONB,
              report     JSONB,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def get_chain_state(user_id: int) -> dict[str, Any]:
    ensure_chain_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT idea, draft, report, updated_at FROM ai_chain_state WHERE user_id = %s",
            (int(user_id),),
        ).fetchone()
    if not row:
        return {"ok": True, "state": None}
    return {
        "ok": True,
        "state": {
            "idea": row["idea"],
            "draft": row["draft"],
            "report": row["report"],
            "updated_at": row["updated_at"].isoformat(),
        },
    }


def merge_chain_state(
    current: dict[str, Any] | None, patch: dict[str, Any]
) -> dict[str, Any]:
    """只合并 patch 里出现的 key；显式 null 表示清空该段。"""
    out = dict(current or {})
    for key in _KEYS:
        if key in patch:
            out[key] = patch[key]
    return out


def put_chain_state(user_id: int, patch: dict[str, Any]) -> dict[str, Any]:
    ensure_chain_schema()
    existing = get_chain_state(user_id)["state"] or {}
    merged = merge_chain_state(existing, patch)
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO ai_chain_state (user_id, idea, draft, report, updated_at)
            VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
              idea = EXCLUDED.idea,
              draft = EXCLUDED.draft,
              report = EXCLUDED.report,
              updated_at = NOW()
            RETURNING updated_at
            """,
            (
                int(user_id),
                json.dumps(merged.get("idea"), ensure_ascii=False),
                json.dumps(merged.get("draft"), ensure_ascii=False),
                json.dumps(merged.get("report"), ensure_ascii=False),
            ),
        ).fetchone()
    return {"ok": True, "updated_at": row["updated_at"].isoformat()}


def delete_chain_state(user_id: int) -> dict[str, Any]:
    ensure_chain_schema()
    with get_conn() as conn:
        conn.execute("DELETE FROM ai_chain_state WHERE user_id = %s", (int(user_id),))
    return {"ok": True}
