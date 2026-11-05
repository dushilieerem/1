# -*- coding: utf-8 -*-
"""Agent 提示词覆盖与 AI 结果缓存。

- 提示词覆盖按 task_id 存全局版本；管理员保存后版本 +1。
- 结果缓存按任务 + 归属 + 对象 + 输入 hash + 提示词版本去重。
- 表结构懒初始化，避免改 main.py / migrations。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from psycopg.types.json import Jsonb

from services.core.db import get_conn

_SCHEMA_READY = False


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_ai_agent_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_agent_prompt (
              id           BIGSERIAL PRIMARY KEY,
              task_id      TEXT NOT NULL,
              scope        TEXT NOT NULL DEFAULT 'global',
              owner_id     BIGINT NOT NULL DEFAULT 0,
              version_no   INTEGER NOT NULL,
              action       TEXT NOT NULL DEFAULT 'save',
              prompt       TEXT NOT NULL,
              prompt_hash  TEXT NOT NULL,
              status       TEXT NOT NULL DEFAULT 'active',
              note         TEXT,
              updated_by   BIGINT,
              created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT ai_agent_prompt_scope_chk CHECK (scope IN ('global','user')),
              CONSTRAINT ai_agent_prompt_action_chk CHECK (action IN ('save','reset')),
              CONSTRAINT ai_agent_prompt_status_chk CHECK (status IN ('active','archived')),
              CONSTRAINT ai_agent_prompt_version_key UNIQUE (task_id, scope, owner_id, version_no)
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_agent_prompt_active "
            "ON ai_agent_prompt (task_id, scope, owner_id) WHERE status='active'"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_agent_prompt_history "
            "ON ai_agent_prompt (task_id, scope, owner_id, version_no DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_agent_output (
              id            BIGSERIAL PRIMARY KEY,
              task_id       TEXT NOT NULL,
              org_id        BIGINT NOT NULL DEFAULT 0,
              scope_key     TEXT NOT NULL,
              input_hash    TEXT NOT NULL,
              prompt_version TEXT NOT NULL DEFAULT '0',
              output        JSONB NOT NULL,
              engine        TEXT,
              created_by    BIGINT,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT ai_agent_output_key UNIQUE (task_id, org_id, scope_key, input_hash, prompt_version)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_agent_output_subject "
            "ON ai_agent_output (task_id, org_id, scope_key, updated_at DESC)"
        )
    _SCHEMA_READY = True


def get_effective_prompt(task_id: str, default: str) -> tuple[str, str]:
    """返回 (提示词, 版本)。无覆盖/DB 异常时使用代码默认值。"""
    try:
        ensure_ai_agent_schema()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT prompt, version_no FROM ai_agent_prompt "
                "WHERE task_id=%s AND scope='global' AND owner_id=0 AND status='active' "
                "ORDER BY version_no DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        if row and str(row["prompt"] or "").strip():
            return str(row["prompt"]), str(row["version_no"])
    except Exception:
        pass
    return default, "0"


def get_active_prompt(task_id: str) -> dict[str, Any] | None:
    try:
        ensure_ai_agent_schema()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT version_no, prompt, prompt_hash, updated_by, created_at "
                "FROM ai_agent_prompt WHERE task_id=%s AND scope='global' AND owner_id=0 "
                "AND status='active' ORDER BY version_no DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def save_prompt(
    task_id: str,
    prompt: str,
    *,
    updated_by: int | None,
    note: str | None = None,
) -> dict[str, Any]:
    text = str(prompt or "").strip()
    if not text:
        raise ValueError("提示词不能为空")
    ensure_ai_agent_schema()
    with get_conn() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{task_id}:global:0",))
        conn.execute(
            "UPDATE ai_agent_prompt SET status='archived' "
            "WHERE task_id=%s AND scope='global' AND owner_id=0 AND status='active'",
            (task_id,),
        )
        row = conn.execute(
            "SELECT COALESCE(MAX(version_no),0)+1 AS n FROM ai_agent_prompt "
            "WHERE task_id=%s AND scope='global' AND owner_id=0",
            (task_id,),
        ).fetchone()
        version = int(row["n"])
        conn.execute(
            """
            INSERT INTO ai_agent_prompt
              (task_id, scope, owner_id, version_no, action, prompt, prompt_hash, status, note, updated_by)
            VALUES (%s,'global',0,%s,'save',%s,%s,'active',%s,%s)
            """,
            (task_id, version, text, _hash(text), note, updated_by),
        )
    return {"task_id": task_id, "version": version, "prompt_hash": _hash(text)}


def reset_prompt(task_id: str, *, updated_by: int | None = None) -> dict[str, Any]:
    ensure_ai_agent_schema()
    with get_conn() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{task_id}:global:0",))
        conn.execute(
            "UPDATE ai_agent_prompt SET status='archived' "
            "WHERE task_id=%s AND scope='global' AND owner_id=0 AND status='active'",
            (task_id,),
        )
        row = conn.execute(
            "SELECT COALESCE(MAX(version_no),0)+1 AS n FROM ai_agent_prompt "
            "WHERE task_id=%s AND scope='global' AND owner_id=0",
            (task_id,),
        ).fetchone()
        version = int(row["n"])
        conn.execute(
            """
            INSERT INTO ai_agent_prompt
              (task_id, scope, owner_id, version_no, action, prompt, prompt_hash, status, note, updated_by)
            VALUES (%s,'global',0,%s,'reset','[reset to default]',%s,'archived','reset',%s)
            """,
            (task_id, version, _hash("[reset to default]"), updated_by),
        )
    return {"task_id": task_id, "version": version, "reset": True}


def list_prompt_history(task_id: str, limit: int = 20) -> list[dict[str, Any]]:
    ensure_ai_agent_schema()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, version_no, action, prompt, status, note, updated_by, created_at "
            "FROM ai_agent_prompt WHERE task_id=%s AND scope='global' AND owner_id=0 "
            "ORDER BY version_no DESC LIMIT %s",
            (task_id, max(1, min(int(limit), 100))),
        ).fetchall()
    return [dict(r) for r in rows]


def get_cached_output(
    task_id: str,
    *,
    org_id: int,
    scope_key: str,
    input_hash: str,
    prompt_version: str,
) -> dict[str, Any] | None:
    try:
        ensure_ai_agent_schema()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT output, engine, created_at, updated_at FROM ai_agent_output "
                "WHERE task_id=%s AND org_id=%s AND scope_key=%s AND input_hash=%s AND prompt_version=%s",
                (task_id, org_id, scope_key, input_hash, prompt_version),
            ).fetchone()
        if not row:
            return None
        out = row["output"] if isinstance(row["output"], dict) else json.loads(row["output"] or "{}")
        return {
            "output": out,
            "engine": row["engine"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
    except Exception:
        return None


def get_latest_output(
    task_id: str,
    *,
    org_id: int,
    scope_key: str,
) -> dict[str, Any] | None:
    """同一 scope 下最近一次生成结果。

    不按 input_hash/prompt_version 过滤：提示词或输入变化时，旧结论仍是已生成的
    业务资产，读页面应直接展示；用户点「重新生成」才覆盖。
    """
    try:
        ensure_ai_agent_schema()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT output, engine, input_hash, prompt_version, created_at, updated_at "
                "FROM ai_agent_output WHERE task_id=%s AND org_id=%s AND scope_key=%s "
                "ORDER BY updated_at DESC, id DESC LIMIT 1",
                (task_id, org_id, scope_key),
            ).fetchone()
        if not row:
            return None
        out = row["output"] if isinstance(row["output"], dict) else json.loads(row["output"] or "{}")
        return {
            "output": out,
            "engine": row["engine"],
            "input_hash": row["input_hash"],
            "prompt_version": row["prompt_version"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
    except Exception:
        return None


def save_output(
    task_id: str,
    *,
    org_id: int,
    scope_key: str,
    input_hash: str,
    prompt_version: str,
    output: dict[str, Any],
    engine: str | None,
    created_by: int | None,
) -> None:
    ensure_ai_agent_schema()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ai_agent_output
              (task_id, org_id, scope_key, input_hash, prompt_version, output, engine, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (task_id, org_id, scope_key, input_hash, prompt_version)
            DO UPDATE SET output=EXCLUDED.output, engine=EXCLUDED.engine, updated_at=NOW()
            """,
            (task_id, org_id, scope_key, input_hash, prompt_version, Jsonb(output), engine, created_by),
        )


def input_hash(payload: Any, prompt: str) -> str:
    """输入 + 提示词共同决定缓存 key；提示词改了自然失效。"""
    return _hash({"payload": payload, "prompt_hash": _hash(prompt)})
