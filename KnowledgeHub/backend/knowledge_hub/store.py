# -*- coding: utf-8 -*-
"""知识库平台表：集合 / 文档 / 切片 / 聊天助手 / 模型供应商。"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_hub.chunking import chunk_text
from services.core.db import get_conn

# 解析进度（内存），供前端轮询；ThreadingHTTPServer 下可边 ingest 边读
_INGEST_PROGRESS: dict[int, dict[str, Any]] = {}
_INGEST_PROGRESS_LOCK = threading.Lock()


def _set_ingest_progress(
    doc_id: int,
    *,
    phase: str,
    done: int = 0,
    total: int = 0,
    title: str = "",
    message: str = "",
    percent: int | None = None,
) -> None:
    did = int(doc_id)
    if percent is None:
        if phase in ("done", "error"):
            percent = 100 if phase == "done" else 0
        elif phase == "chunking":
            percent = 5
        elif phase == "embedding":
            percent = 8 + int(87 * (done / total)) if total > 0 else 8
        elif phase == "saving":
            percent = 96
        else:
            percent = 1
    payload = {
        "documentId": did,
        "phase": phase,
        "done": int(done),
        "total": int(total),
        "percent": max(0, min(100, int(percent))),
        "title": title or "",
        "message": message or "",
        "updatedAt": time.time(),
    }
    with _INGEST_PROGRESS_LOCK:
        _INGEST_PROGRESS[did] = payload


def get_ingest_progress(doc_id: int) -> dict[str, Any]:
    with _INGEST_PROGRESS_LOCK:
        cur = _INGEST_PROGRESS.get(int(doc_id))
        if cur:
            return dict(cur)
    return {
        "documentId": int(doc_id),
        "phase": "idle",
        "done": 0,
        "total": 0,
        "percent": 0,
        "title": "",
        "message": "",
    }


def _clear_ingest_progress(doc_id: int, delay_sec: float = 2.0) -> None:
    """完成后短暂保留，便于前端读到 100%，再清掉。"""

    def _later() -> None:
        time.sleep(delay_sec)
        with _INGEST_PROGRESS_LOCK:
            _INGEST_PROGRESS.pop(int(doc_id), None)

    threading.Thread(target=_later, daemon=True).start()

# 知识库类型（原 RAGFlow pipeline）→ 默认分块
PIPELINES: list[dict[str, Any]] = [
    {"id": "general", "labelZh": "通用", "defaultChunk": "plain_window"},
    {"id": "qa", "labelZh": "问答", "defaultChunk": "qa_pair"},
    {"id": "manual", "labelZh": "手册", "defaultChunk": "markdown_heading"},
    {"id": "table", "labelZh": "表格", "defaultChunk": "table_row"},
    {"id": "paper", "labelZh": "论文", "defaultChunk": "structured_fields"},
    {"id": "laws", "labelZh": "法规", "defaultChunk": "markdown_heading"},
]


def list_pipelines() -> list[dict[str, Any]]:
    return list(PIPELINES)


# 进程内只做一次建表/迁移，避免首页 Promise.all 并发撞死锁
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False
_KH_MIGRATE_ADVISORY_KEY = 87060401  # 任意稳定 int64


def _iso(val: Any) -> Any:
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def _migrate_chat_conversations(conn: Any) -> None:
    """为每个聊天应用保证至少有一个会话，并把无 conversation_id 的旧消息挂上去。

    须在持有 advisory lock 时调用；无活可干则立即返回。
    """
    need_msgs = conn.execute(
        """
        SELECT 1 FROM kh_chat_messages
        WHERE conversation_id IS NULL
        LIMIT 1
        """
    ).fetchone()
    need_chats = conn.execute(
        """
        SELECT c.id
        FROM kh_chats c
        WHERE NOT EXISTS (
          SELECT 1 FROM kh_conversations v WHERE v.chat_id = c.id
        )
        ORDER BY c.id
        """
    ).fetchall()
    if not need_msgs and not need_chats:
        return

    # 按 chat_id 升序处理，降低并发锁顺序交叉概率
    chats = conn.execute("SELECT id FROM kh_chats ORDER BY id ASC").fetchall()
    for ch in chats:
        chat_id = int(ch["id"])
        row = conn.execute(
            """
            SELECT id FROM kh_conversations
            WHERE chat_id = %s
            ORDER BY id ASC
            LIMIT 1
            """,
            (chat_id,),
        ).fetchone()
        if row:
            conv_id = int(row["id"])
        else:
            created = conn.execute(
                """
                INSERT INTO kh_conversations (chat_id, title)
                VALUES (%s, %s)
                RETURNING id
                """,
                (chat_id, "默认会话"),
            ).fetchone()
            conv_id = int(created["id"])
        conn.execute(
            """
            UPDATE kh_chat_messages
            SET conversation_id = %s
            WHERE chat_id = %s AND conversation_id IS NULL
            """,
            (conv_id, chat_id),
        )


def ensure_kh_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with get_conn() as conn:
            # 跨请求/进程串行化 DDL + 迁移（首页会并行打多个 /api/kh/*）
            conn.execute(
                "SELECT pg_advisory_lock(%s)", (_KH_MIGRATE_ADVISORY_KEY,)
            )
            try:
                _ensure_kh_schema_unlocked(conn)
            finally:
                conn.execute(
                    "SELECT pg_advisory_unlock(%s)", (_KH_MIGRATE_ADVISORY_KEY,)
                )
        _SCHEMA_READY = True


def _ensure_kh_schema_unlocked(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_collections (
          id              BIGSERIAL PRIMARY KEY,
          name            TEXT NOT NULL UNIQUE,
          description     TEXT NOT NULL DEFAULT '',
          pipeline        TEXT NOT NULL DEFAULT 'general',
          chunk_strategy  TEXT NOT NULL DEFAULT 'plain_window',
          status          TEXT NOT NULL DEFAULT 'active',
          created_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_documents (
          id              BIGSERIAL PRIMARY KEY,
          collection_id   BIGINT NOT NULL
            REFERENCES kh_collections(id) ON DELETE CASCADE,
          title           TEXT NOT NULL,
          source_type     TEXT NOT NULL DEFAULT 'text',
          body            TEXT NOT NULL DEFAULT '',
          file_name       TEXT NOT NULL DEFAULT '',
          file_size       BIGINT NOT NULL DEFAULT 0,
          chunk_strategy  TEXT NOT NULL DEFAULT 'plain_window',
          status          TEXT NOT NULL DEFAULT 'draft',
          enabled         BOOLEAN NOT NULL DEFAULT TRUE,
          parse_error     TEXT NOT NULL DEFAULT '',
          version         INT NOT NULL DEFAULT 1,
          created_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kh_documents_coll "
        "ON kh_documents (collection_id, updated_at DESC)"
    )
    # 旧库补列：启用开关 / 解析错误
    for col_name, ddl in (
        ("enabled", "ALTER TABLE kh_documents ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE"),
        ("parse_error", "ALTER TABLE kh_documents ADD COLUMN parse_error TEXT NOT NULL DEFAULT ''"),
    ):
        exists = conn.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'kh_documents' AND column_name = %s
            """,
            (col_name,),
        ).fetchone()
        if not exists:
            conn.execute(ddl)
    for col_name, ddl in (
        ("ingest_mode", "ALTER TABLE kh_documents ADD COLUMN ingest_mode TEXT NOT NULL DEFAULT 'plain'"),
        ("domain", "ALTER TABLE kh_documents ADD COLUMN domain TEXT NOT NULL DEFAULT ''"),
        ("payload", "ALTER TABLE kh_documents ADD COLUMN payload JSONB"),
        (
            "attachment_file_id",
            "ALTER TABLE kh_documents ADD COLUMN attachment_file_id BIGINT",
        ),
    ):
        exists = conn.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'kh_documents' AND column_name = %s
            """,
            (col_name,),
        ).fetchone()
        if not exists:
            conn.execute(ddl)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_attachments (
          id              BIGSERIAL PRIMARY KEY,
          file_name       TEXT NOT NULL DEFAULT '',
          mime_type       TEXT NOT NULL DEFAULT 'application/octet-stream',
          size_bytes      BIGINT NOT NULL DEFAULT 0,
          storage_path    TEXT NOT NULL DEFAULT '',
          sha256          TEXT NOT NULL DEFAULT '',
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_chunks (
          id            BIGSERIAL PRIMARY KEY,
          document_id   BIGINT NOT NULL
            REFERENCES kh_documents(id) ON DELETE CASCADE,
          ordinal       INT NOT NULL,
          text          TEXT NOT NULL,
          meta          JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          UNIQUE (document_id, ordinal)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_files (
          id              BIGSERIAL PRIMARY KEY,
          title           TEXT NOT NULL,
          file_name       TEXT NOT NULL DEFAULT '',
          file_size       BIGINT NOT NULL DEFAULT 0,
          body            TEXT NOT NULL DEFAULT '',
          collection_id   BIGINT REFERENCES kh_collections(id) ON DELETE SET NULL,
          created_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_chats (
          id              BIGSERIAL PRIMARY KEY,
          name            TEXT NOT NULL,
          description     TEXT NOT NULL DEFAULT '',
          opener          TEXT NOT NULL DEFAULT '你好！我是你的助理，有什么可以帮到你的吗？',
          system_prompt   TEXT NOT NULL DEFAULT '',
          empty_response  TEXT NOT NULL DEFAULT '',
          collection_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
          model_name      TEXT NOT NULL DEFAULT '',
          temperature     REAL,
          top_p           REAL,
          max_tokens      INT,
          created_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_conversations (
          id              BIGSERIAL PRIMARY KEY,
          chat_id         BIGINT NOT NULL REFERENCES kh_chats(id) ON DELETE CASCADE,
          title           TEXT NOT NULL DEFAULT '新会话',
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kh_conversations_chat
          ON kh_conversations (chat_id, updated_at DESC)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_chat_messages (
          id              BIGSERIAL PRIMARY KEY,
          chat_id         BIGINT NOT NULL REFERENCES kh_chats(id) ON DELETE CASCADE,
          conversation_id BIGINT REFERENCES kh_conversations(id) ON DELETE CASCADE,
          role            TEXT NOT NULL,
          content         TEXT NOT NULL DEFAULT '',
          meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # 旧库补列（CREATE IF NOT EXISTS 不会改已有表）
    col = conn.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'kh_chat_messages' AND column_name = 'conversation_id'
        """
    ).fetchone()
    if not col:
        conn.execute(
            """
            ALTER TABLE kh_chat_messages
              ADD COLUMN conversation_id BIGINT
              REFERENCES kh_conversations(id) ON DELETE CASCADE
            """
        )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kh_chat_messages_chat_id
          ON kh_chat_messages (chat_id, id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kh_chat_messages_conv_id
          ON kh_chat_messages (conversation_id, id)
        """
    )
    _migrate_chat_conversations(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_model_providers (
          id            BIGSERIAL PRIMARY KEY,
          provider_key  TEXT NOT NULL UNIQUE,
          display_name  TEXT NOT NULL,
          base_url      TEXT NOT NULL DEFAULT '',
          api_key       TEXT NOT NULL DEFAULT '',
          models        JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kh_default_models (
          id            BIGSERIAL PRIMARY KEY,
          role_key      TEXT NOT NULL UNIQUE,
          provider_key  TEXT NOT NULL DEFAULT '',
          model_name    TEXT NOT NULL DEFAULT '',
          updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _coll_row(r: dict[str, Any], doc_count: int = 0) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "name": r["name"],
        "description": r.get("description") or "",
        "pipeline": r.get("pipeline") or "general",
        "chunkStrategy": r.get("chunk_strategy") or "plain_window",
        "status": r.get("status") or "active",
        "documentCount": int(doc_count),
        "createdAt": _iso(r.get("created_at")),
        "updatedAt": _iso(r.get("updated_at")),
    }


def list_collections() -> list[dict[str, Any]]:
    ensure_kh_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.*, COALESCE(d.cnt, 0) AS document_count
            FROM kh_collections c
            LEFT JOIN (
              SELECT collection_id, COUNT(*) AS cnt
              FROM kh_documents GROUP BY collection_id
            ) d ON d.collection_id = c.id
            ORDER BY c.updated_at DESC
            """
        ).fetchall()
    return [_coll_row(dict(r), int(dict(r).get("document_count") or 0)) for r in rows]


def create_collection(
    *,
    name: str,
    description: str = "",
    pipeline: str = "general",
    chunk_strategy: str | None = None,
    created_by: int | None = None,
) -> dict[str, Any]:
    ensure_kh_schema()
    title = (name or "").strip()
    if not title:
        raise ValueError("请填写知识库名称")
    pipe = (pipeline or "general").strip()
    pipe_meta = next((p for p in PIPELINES if p["id"] == pipe), None)
    if not pipe_meta:
        raise ValueError(f"未知知识库类型: {pipe}")
    strategy = (chunk_strategy or pipe_meta["defaultChunk"]).strip()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO kh_collections
              (name, description, pipeline, chunk_strategy, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (title, description or "", pipe, strategy, created_by),
        ).fetchone()
    return _coll_row(dict(row), 0)


def delete_collection(coll_id: int) -> bool:
    ensure_kh_schema()
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM kh_collections WHERE id = %s RETURNING id", (int(coll_id),)
        )
        return bool(cur.fetchone())


def update_collection(coll_id: int, body: dict[str, Any]) -> dict[str, Any]:
    ensure_kh_schema()
    sets: list[str] = []
    vals: list[Any] = []
    if "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            raise ValueError("名称不能为空")
        sets.append("name = %s")
        vals.append(name)
    if "description" in body:
        sets.append("description = %s")
        vals.append(str(body.get("description") or ""))
    if "pipeline" in body:
        pipe = str(body.get("pipeline") or "").strip()
        if pipe and not any(p["id"] == pipe for p in PIPELINES):
            raise ValueError(f"未知知识库类型: {pipe}")
        if pipe:
            sets.append("pipeline = %s")
            vals.append(pipe)
    if "chunkStrategy" in body or "chunk_strategy" in body:
        strategy = str(body.get("chunkStrategy") or body.get("chunk_strategy") or "").strip()
        if strategy:
            sets.append("chunk_strategy = %s")
            vals.append(strategy)
    if not sets:
        raise ValueError("没有可更新字段")
    sets.append("updated_at = NOW()")
    vals.append(int(coll_id))
    with get_conn() as conn:
        row = conn.execute(
            f"UPDATE kh_collections SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(vals),
        ).fetchone()
        if not row:
            raise KeyError("知识库不存在")
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM kh_documents WHERE collection_id = %s",
            (int(coll_id),),
        ).fetchone()
    return _coll_row(dict(row), int(dict(cnt).get("c") or 0) if cnt else 0)


def update_document(doc_id: int, body: dict[str, Any]) -> dict[str, Any]:
    ensure_kh_schema()
    sets: list[str] = []
    vals: list[Any] = []
    if "title" in body:
        title = str(body.get("title") or "").strip()
        if not title:
            raise ValueError("标题不能为空")
        sets.append("title = %s")
        vals.append(title)
    if "fileName" in body or "file_name" in body:
        sets.append("file_name = %s")
        vals.append(str(body.get("fileName") or body.get("file_name") or ""))
    if "enabled" in body:
        sets.append("enabled = %s")
        vals.append(bool(body.get("enabled")))
    if not sets:
        raise ValueError("没有可更新字段")
    sets.append("updated_at = NOW()")
    vals.append(int(doc_id))
    with get_conn() as conn:
        row = conn.execute(
            f"UPDATE kh_documents SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(vals),
        ).fetchone()
        if not row:
            raise KeyError("文档不存在")
    return _doc_row(dict(row), include_body=False)


def _doc_row(r: dict[str, Any], *, include_body: bool = False) -> dict[str, Any]:
    payload = r.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = None
    ingest_mode = (r.get("ingest_mode") or "plain").strip() or "plain"
    attachment_id = r.get("attachment_file_id")
    out: dict[str, Any] = {
        "id": int(r["id"]),
        "collectionId": int(r["collection_id"]),
        "title": r["title"],
        "sourceType": r.get("source_type") or "text",
        "ingestMode": ingest_mode,
        "domain": r.get("domain") or "",
        "fileName": r.get("file_name") or "",
        "fileSize": int(r.get("file_size") or 0),
        "chunkStrategy": r.get("chunk_strategy") or "plain_window",
        "status": r.get("status") or "draft",
        "enabled": bool(r["enabled"]) if r.get("enabled") is not None else True,
        "parseError": (r.get("parse_error") or "")[:500],
        "version": int(r.get("version") or 1),
        "hasAttachment": bool(attachment_id),
        "attachmentFileId": int(attachment_id) if attachment_id else None,
        "createdAt": _iso(r.get("created_at")),
        "updatedAt": _iso(r.get("updated_at")),
    }
    if include_body:
        out["body"] = r.get("body") or ""
        if payload is not None:
            out["payload"] = payload
    else:
        body = r.get("body") or ""
        out["bodyPreview"] = body[:160] + ("…" if len(body) > 160 else "")
    return out


def list_documents(collection_id: int) -> list[dict[str, Any]]:
    ensure_kh_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.*, COALESCE(c.cnt, 0) AS chunk_count
            FROM kh_documents d
            LEFT JOIN (
              SELECT document_id, COUNT(*) AS cnt FROM kh_chunks GROUP BY document_id
            ) c ON c.document_id = d.id
            WHERE d.collection_id = %s
            ORDER BY d.updated_at DESC
            """,
            (int(collection_id),),
        ).fetchall()
        # 按文档汇总 Embedding 状态（不回传大向量）
        embed_rows = conn.execute(
            """
            SELECT c.document_id,
                   COUNT(*) FILTER (
                     WHERE c.meta ? 'embedding'
                       AND jsonb_typeof(c.meta->'embedding') = 'array'
                   ) AS with_vec,
                   COUNT(*) FILTER (WHERE c.meta ? 'embedError') AS with_err,
                   COUNT(*) AS total
            FROM kh_chunks c
            JOIN kh_documents d ON d.id = c.document_id
            WHERE d.collection_id = %s
            GROUP BY c.document_id
            """,
            (int(collection_id),),
        ).fetchall()
    embed_by: dict[int, dict[str, int]] = {}
    for er in embed_rows:
        embed_by[int(er["document_id"])] = {
            "with_vec": int(er["with_vec"] or 0),
            "with_err": int(er["with_err"] or 0),
            "total": int(er["total"] or 0),
        }
    out = []
    for r in rows:
        item = _doc_row(dict(r))
        item["chunkCount"] = int(dict(r).get("chunk_count") or 0)
        st = embed_by.get(int(r["id"]))
        if not st or st["total"] == 0:
            item["embedStatus"] = "none"
        elif st["with_err"] > 0 and st["with_vec"] == 0:
            item["embedStatus"] = "error"
        elif st["with_vec"] > 0:
            item["embedStatus"] = "ready"
        else:
            item["embedStatus"] = "none"
        out.append(item)
    return out


def create_document(
    *,
    collection_id: int,
    title: str,
    body: str = "",
    chunk_strategy: str | None = None,
    source_type: str = "text",
    file_name: str = "",
    file_size: int = 0,
    created_by: int | None = None,
    ingest: bool = True,
    content_base64: str | None = None,
) -> dict[str, Any]:
    ensure_kh_schema()
    title = (title or "").strip() or "未命名文档"
    body = body or ""
    fname = file_name or ""

    if content_base64 and not body.strip():
        import base64

        from knowledge_hub.extractors import extract_text, is_binary_doc

        if not is_binary_doc(fname):
            raise ValueError("contentBase64 仅用于 .docx / .pdf")
        try:
            raw = base64.b64decode(content_base64, validate=False)
        except Exception as exc:
            raise ValueError(f"文件解码失败：{exc}") from exc
        if file_size <= 0:
            file_size = len(raw)
        body = extract_text(fname, raw)
        source_type = source_type or Path(fname).suffix.lower().lstrip(".") or "file"

    if not body.strip():
        raise ValueError("正文不能为空")
    with get_conn() as conn:
        coll = conn.execute(
            "SELECT id, chunk_strategy FROM kh_collections WHERE id = %s",
            (int(collection_id),),
        ).fetchone()
        if not coll:
            raise ValueError("知识库不存在")
        strategy = (chunk_strategy or coll["chunk_strategy"] or "plain_window").strip()
        row = conn.execute(
            """
            INSERT INTO kh_documents
              (collection_id, title, source_type, body, file_name, file_size,
               chunk_strategy, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft', %s)
            RETURNING *
            """,
            (
                int(collection_id),
                title,
                source_type or "text",
                body,
                file_name or "",
                int(file_size or 0),
                strategy,
                created_by,
            ),
        ).fetchone()
        conn.execute(
            "UPDATE kh_collections SET updated_at = NOW() WHERE id = %s",
            (int(collection_id),),
        )
    doc = _doc_row(dict(row), include_body=True)
    if ingest:
        ingest_document(int(doc["id"]))
        got = get_document(int(doc["id"]))
        return got or doc
    return doc


def create_structured_document(
    *,
    collection_id: int,
    domain: str,
    payload: dict[str, Any],
    created_by: int | None = None,
    ingest: bool = True,
    chunk_strategy: str | None = None,
    attachment_base64: str | None = None,
    attachment_file_name: str = "",
) -> dict[str, Any]:
    """结构化填报入库：payload 分块索引；附件可选且不抽字。"""
    ensure_kh_schema()
    from knowledge_hub.attachments import save_attachment_bytes
    from knowledge_hub.payload_utils import (
        iter_structured_field_chunks,
        render_payload_preview,
        storage_payload_dict,
    )
    from knowledge_hub.schemas.knowledge_unit import parse_knowledge_unit_payload

    domain = (domain or "paper").strip() or "paper"
    ku = parse_knowledge_unit_payload(payload)
    title = (ku.document.title or "").strip()
    if not title:
        raise ValueError("标题不能为空")
    storage = storage_payload_dict(ku)
    preview = render_payload_preview(ku)
    strategy = (chunk_strategy or "structured_fields").strip() or "structured_fields"
    if strategy == "structured_fields":
        pieces = iter_structured_field_chunks(ku)
        if not pieces:
            raise ValueError("至少填写一个可用于检索的字段")
    elif not preview.strip():
        raise ValueError("至少填写一个可用于检索的字段")

    attachment_id: int | None = None
    fname = attachment_file_name or ""
    fsize = 0
    if attachment_base64:
        import base64

        try:
            raw = base64.b64decode(attachment_base64, validate=False)
        except Exception as exc:
            raise ValueError(f"附件解码失败：{exc}") from exc
        if not fname.strip():
            raise ValueError("上传附件时需填写文件名")
        att = save_attachment_bytes(raw, fname)
        attachment_id = int(att["id"])
        fname = att["fileName"]
        fsize = int(att["sizeBytes"])

    with get_conn() as conn:
        coll = conn.execute(
            "SELECT id FROM kh_collections WHERE id = %s", (int(collection_id),)
        ).fetchone()
        if not coll:
            raise ValueError("知识库不存在")
        row = conn.execute(
            """
            INSERT INTO kh_documents
              (collection_id, title, source_type, body, file_name, file_size,
               chunk_strategy, status, created_by, ingest_mode, domain, payload,
               attachment_file_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft', %s, 'structured', %s, %s::jsonb, %s)
            RETURNING *
            """,
            (
                int(collection_id),
                title,
                "structured",
                preview,
                fname,
                int(fsize),
                strategy,
                created_by,
                domain,
                json.dumps(storage, ensure_ascii=False),
                attachment_id,
            ),
        ).fetchone()
        conn.execute(
            "UPDATE kh_collections SET updated_at = NOW() WHERE id = %s",
            (int(collection_id),),
        )
    doc = _doc_row(dict(row), include_body=True)
    if ingest:
        ingest_document(int(doc["id"]))
        got = get_document(int(doc["id"]))
        return got or doc
    return doc


def get_document(doc_id: int) -> dict[str, Any] | None:
    ensure_kh_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM kh_documents WHERE id = %s", (int(doc_id),)
        ).fetchone()
    return _doc_row(dict(row), include_body=True) if row else None


def delete_document(doc_id: int) -> bool:
    ensure_kh_schema()
    attachment_id: int | None = None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT attachment_file_id FROM kh_documents WHERE id = %s",
            (int(doc_id),),
        ).fetchone()
        if row and row.get("attachment_file_id"):
            attachment_id = int(row["attachment_file_id"])
        cur = conn.execute(
            "DELETE FROM kh_documents WHERE id = %s RETURNING id", (int(doc_id),)
        )
        ok = bool(cur.fetchone())
    if ok and attachment_id:
        from knowledge_hub.attachments import delete_attachment

        try:
            delete_attachment(attachment_id)
        except Exception:
            pass
    return ok


def ingest_document(doc_id: int) -> dict[str, Any]:
    ensure_kh_schema()
    from knowledge_hub.embedding import embed_texts, get_role_credentials

    did = int(doc_id)
    title = ""
    try:
        with get_conn() as conn:
            doc = conn.execute(
                "SELECT * FROM kh_documents WHERE id = %s", (did,)
            ).fetchone()
            if not doc:
                raise ValueError("文档不存在")
            title = str(doc.get("title") or "")
            conn.execute(
                """
                UPDATE kh_documents
                SET status = 'parsing', parse_error = '', updated_at = NOW()
                WHERE id = %s
                """,
                (did,),
            )

        _set_ingest_progress(
            did,
            phase="chunking",
            title=title,
            message="正在分块…",
            percent=5,
        )

        with get_conn() as conn:
            doc = conn.execute(
                "SELECT * FROM kh_documents WHERE id = %s", (did,)
            ).fetchone()
            if not doc:
                raise ValueError("文档不存在")
            ingest_mode = (doc.get("ingest_mode") or "plain").strip() or "plain"
            strategy = (doc.get("chunk_strategy") or "plain_window").strip()
            if ingest_mode == "structured" and strategy == "structured_fields":
                from knowledge_hub.payload_utils import iter_structured_field_chunks

                raw_payload = doc.get("payload")
                if isinstance(raw_payload, str):
                    raw_payload = json.loads(raw_payload)
                if not isinstance(raw_payload, dict):
                    raise ValueError("结构化文档缺少 payload")
                pieces = iter_structured_field_chunks(raw_payload)
                if not pieces:
                    raise ValueError("没有可用于检索的非空字段")
            else:
                pieces = chunk_text(doc["body"] or "", strategy or "plain_window")
            conn.execute("DELETE FROM kh_chunks WHERE document_id = %s", (did,))

            embed_ok = 0
            embed_err: str | None = None
            vectors: list[list[float] | None] = [None] * len(pieces)
            creds = get_role_credentials("embedding")
            if creds and pieces:
                _set_ingest_progress(
                    did,
                    phase="embedding",
                    done=0,
                    total=len(pieces),
                    title=title,
                    message=f"正在向量化 0/{len(pieces)}…",
                )

                def _on_emb(done: int, total: int) -> None:
                    _set_ingest_progress(
                        did,
                        phase="embedding",
                        done=done,
                        total=total,
                        title=title,
                        message=f"正在向量化 {done}/{total}…",
                    )

                try:
                    vectors = embed_texts(
                        [p["text"] for p in pieces],
                        creds=creds,
                        on_progress=_on_emb,
                    )
                    embed_ok = len(vectors)
                except Exception as e:
                    embed_err = str(e)[:400]
                    vectors = [None] * len(pieces)
            elif pieces and not creds:
                _set_ingest_progress(
                    did,
                    phase="saving",
                    done=0,
                    total=len(pieces),
                    title=title,
                    message="未配置 Embedding，仅保存分块…",
                    percent=90,
                )

            _set_ingest_progress(
                did,
                phase="saving",
                done=len(pieces),
                total=len(pieces),
                title=title,
                message="正在写入切片…",
                percent=96,
            )

            for i, p in enumerate(pieces):
                meta = dict(p.get("meta") or {})
                if vectors[i] is not None:
                    meta["embedding"] = vectors[i]
                    meta["embeddingModel"] = creds["modelName"] if creds else ""
                    meta["embeddingDim"] = len(vectors[i] or [])
                elif embed_err:
                    meta["embedError"] = embed_err
                elif not creds:
                    meta["embedSkipped"] = "no_default_embedding"
                conn.execute(
                    """
                    INSERT INTO kh_chunks (document_id, ordinal, text, meta)
                    VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    (
                        did,
                        int(p["ordinal"]),
                        p["text"],
                        json.dumps(meta, ensure_ascii=False),
                    ),
                )
            conn.execute(
                """
                UPDATE kh_documents
                SET status = 'ready', parse_error = '', version = version + 1,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (did,),
            )

        _set_ingest_progress(
            did,
            phase="done",
            done=len(pieces),
            total=len(pieces),
            title=title,
            message="解析完成",
            percent=100,
        )
        _clear_ingest_progress(did)
        return {
            "documentId": did,
            "status": "ready",
            "chunkCount": len(pieces),
            "embeddedCount": embed_ok,
            "embedError": embed_err,
        }
    except Exception as e:
        _set_ingest_progress(
            did,
            phase="error",
            title=title,
            message=str(e)[:200],
            percent=0,
        )
        try:
            with get_conn() as conn:
                conn.execute(
                    """
                    UPDATE kh_documents
                    SET status = 'failed',
                        parse_error = %s,
                        updated_at = NOW()
                    WHERE id = %s AND status = 'parsing'
                    """,
                    (str(e)[:500], did),
                )
        except Exception:
            pass
        _clear_ingest_progress(did, delay_sec=8.0)
        raise


def list_chunks(document_id: int) -> list[dict[str, Any]]:
    ensure_kh_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, document_id, ordinal, text, meta, created_at
            FROM kh_chunks WHERE document_id = %s ORDER BY ordinal
            """,
            (int(document_id),),
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "documentId": int(r["document_id"]),
            "ordinal": int(r["ordinal"]),
            "text": r["text"] or "",
            "meta": r["meta"] if isinstance(r["meta"], dict) else {},
            "createdAt": _iso(r["created_at"]),
        }
        for r in rows
    ]


def _tokenize_query(q: str) -> list[str]:
    raw = (q or "").strip()
    if not raw:
        return []
    # 空格 / 标点切分；保留较长中文连续串
    parts = re.split(r"[\s,，。；;、？?！!|/\\]+", raw)
    tokens: list[str] = []
    for p in parts:
        t = p.strip()
        if len(t) >= 1:
            tokens.append(t)
    # 从 schema 字段中文名抽词（加字段时这里自动跟上，不必手维护名单）
    from knowledge_hub.schemas.knowledge_unit import FIELD_LABELS_ZH

    for label in FIELD_LABELS_ZH.values():
        if label and label in raw:
            tokens.append(label)
    for alias in ("局限性", "不足之处", "缺陷"):
        if alias in raw:
            tokens.append(alias)
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out[:24]


# 问句口语别名 → schema field（仅少数同义词；正式中文名走 FIELD_LABELS_ZH）
_STRUCTURED_FIELD_ALIASES: tuple[tuple[str, str], ...] = (
    ("局限性", "limitation"),
    ("不足之处", "limitation"),
    ("缺陷", "limitation"),
    ("limitation", "limitation"),
    ("做法", "what_it_does"),
    ("方法", "what_it_does"),
    ("技术", "ml_tech"),
)


def _hinted_structured_fields(q: str) -> list[str]:
    """问句命中 schema 字段中文名 / 英文字段名 / 少量别名 → 对应 meta.field。"""
    from knowledge_hub.schemas.knowledge_unit import FIELD_LABELS_ZH

    ql = (q or "").lower()
    out: list[str] = []
    seen: set[str] = set()

    # 长 label 优先，避免短串误伤（如「数据」）时仍按出现即记，覆盖补入只在有候选时生效
    labels = sorted(
        ((k, v) for k, v in FIELD_LABELS_ZH.items() if k != "document_meta" and v),
        key=lambda kv: -len(kv[1]),
    )
    for field, label in labels:
        if label.lower() in ql and field not in seen:
            seen.add(field)
            out.append(field)
        if field.lower() in ql and field not in seen:
            seen.add(field)
            out.append(field)
    for hint, field in _STRUCTURED_FIELD_ALIASES:
        if hint.lower() in ql and field not in seen:
            seen.add(field)
            out.append(field)
    return out


def _ensure_structured_field_coverage(
    scored: list[tuple[float, dict[str, Any]]],
    top_k: int,
    hinted_fields: list[str],
) -> list[dict[str, Any]]:
    """问句点到的 schema 字段，尽量让对应切片进入最终 hits（有限集合，随 schema 增长）。"""
    hits = [item for _, item in scored[:top_k]]
    if not hinted_fields or not scored:
        return hits

    def field_of(h: dict[str, Any]) -> str | None:
        meta = h.get("meta") if isinstance(h.get("meta"), dict) else {}
        f = meta.get("field")
        return str(f) if isinstance(f, str) and f else None

    present = {field_of(h) for h in hits}
    for field in hinted_fields:
        if field in present:
            continue
        cand = next((item for _, item in scored if field_of(item) == field), None)
        if not cand:
            continue
        replaced = False
        for i in range(len(hits) - 1, -1, -1):
            f = field_of(hits[i])
            if f not in hinted_fields:
                hits[i] = cand
                present.discard(f)
                present.add(field)
                replaced = True
                break
        if not replaced and hits:
            old = field_of(hits[-1])
            hits[-1] = cand
            present.discard(old)
            present.add(field)
    return hits


def _enrich_hits_with_attachment(hits: list[dict[str, Any]]) -> None:
    if not hits:
        return
    doc_ids = list({int(h["documentId"]) for h in hits})
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.attachment_file_id, d.file_name,
                   a.file_name AS att_name
            FROM kh_documents d
            LEFT JOIN kh_attachments a ON a.id = d.attachment_file_id
            WHERE d.id = ANY(%s)
            """,
            (doc_ids,),
        ).fetchall()
    by_id = {int(r["id"]): dict(r) for r in rows}
    for h in hits:
        row = by_id.get(int(h["documentId"]))
        if row and row.get("attachment_file_id"):
            fn = row.get("att_name") or row.get("file_name") or "attachment"
            h["attachment"] = {
                "available": True,
                "fileName": fn,
                "downloadUrl": f"/api/kh/documents/{int(h['documentId'])}/attachment",
            }
        else:
            h["attachment"] = {"available": False}


def referenced_documents_from_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for h in hits:
        did = int(h["documentId"])
        if did in seen:
            continue
        seen.add(did)
        att = h.get("attachment") if isinstance(h.get("attachment"), dict) else {}
        out.append(
            {
                "documentId": did,
                "documentTitle": h.get("documentTitle") or "",
                "collectionId": h.get("collectionId"),
                "attachment": att,
            }
        )
    return out


def get_document_attachment(doc_id: int) -> tuple[bytes, str, str]:
    """返回 (bytes, file_name, mime_type)。"""
    ensure_kh_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT attachment_file_id FROM kh_documents WHERE id = %s
            """,
            (int(doc_id),),
        ).fetchone()
    if not row or not row.get("attachment_file_id"):
        raise FileNotFoundError("该文档没有可下载的附件")
    from knowledge_hub.attachments import read_attachment

    return read_attachment(int(row["attachment_file_id"]))


def search_chunks(
    *,
    query: str,
    collection_ids: list[int] | None = None,
    top_k: int = 8,
) -> dict[str, Any]:
    """关键词检索；若默认 Embedding 可用且切片含向量，则 hybrid（向量+关键词）。"""
    ensure_kh_schema()
    from knowledge_hub.embedding import cosine, embed_texts, get_role_credentials

    q = (query or "").strip()
    if not q:
        raise ValueError("查询不能为空")
    top_k = max(1, min(int(top_k or 8), 50))
    tokens = _tokenize_query(q)
    if not tokens:
        raise ValueError("查询不能为空")

    cids = [int(x) for x in (collection_ids or []) if x is not None]
    with get_conn() as conn:
        if cids:
            rows = conn.execute(
                """
                SELECT c.id, c.document_id, c.ordinal, c.text, c.meta,
                       d.title AS document_title, d.collection_id, d.status,
                       col.name AS collection_name
                FROM kh_chunks c
                JOIN kh_documents d ON d.id = c.document_id
                JOIN kh_collections col ON col.id = d.collection_id
                WHERE d.status = 'ready'
                  AND COALESCE(d.enabled, TRUE) = TRUE
                  AND d.collection_id = ANY(%s)
                ORDER BY c.id
                """,
                (cids,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.id, c.document_id, c.ordinal, c.text, c.meta,
                       d.title AS document_title, d.collection_id, d.status,
                       col.name AS collection_name
                FROM kh_chunks c
                JOIN kh_documents d ON d.id = c.document_id
                JOIN kh_collections col ON col.id = d.collection_id
                WHERE d.status = 'ready'
                  AND COALESCE(d.enabled, TRUE) = TRUE
                ORDER BY c.id
                """
            ).fetchall()

    q_vec: list[float] | None = None
    mode = "keyword"
    creds = get_role_credentials("embedding")
    has_any_vec = False
    for r in rows:
        meta = r["meta"] if isinstance(r["meta"], dict) else {}
        emb = meta.get("embedding")
        if isinstance(emb, list) and emb:
            has_any_vec = True
            break
    if creds and has_any_vec:
        try:
            q_vec = embed_texts([q], creds=creds)[0]
            mode = "hybrid"
        except Exception:
            q_vec = None
            mode = "keyword"

    scored: list[tuple[float, dict[str, Any]]] = []
    q_lower = q.lower()
    hinted_fields = set(_hinted_structured_fields(q))
    for r in rows:
        text = r["text"] or ""
        title = r["document_title"] or ""
        meta = r["meta"] if isinstance(r["meta"], dict) else {}
        meta_title = str(meta.get("title") or "")
        field = str(meta.get("field") or "") if meta.get("field") else ""
        blob = f"{title}\n{meta_title}\n{text}".lower()
        kw = 0.0
        hit_tokens = 0
        for tok in tokens:
            tl = tok.lower()
            if tl in blob:
                hit_tokens += 1
                kw += 2.0
                kw += min(blob.count(tl), 5) * 0.15
            if tl in meta_title.lower():
                kw += 3.0
            if tl in title.lower():
                kw += 1.5
        if q_lower in blob:
            kw += 4.0
        kw += hit_tokens * 0.5
        # 问句点到的结构化字段：给对应切片加分（短「局限」块否则常被长技术块挤出 TopK）
        if field and field in hinted_fields:
            kw += 6.0

        vec_score = 0.0
        emb = meta.get("embedding")
        if q_vec and isinstance(emb, list) and emb:
            try:
                vec_score = float(cosine(q_vec, [float(x) for x in emb]))
            except Exception:
                vec_score = 0.0

        if mode == "hybrid":
            # 向量为主，关键词作加分（归一到相近量级）
            score = vec_score * 10.0 + min(kw, 12.0) * 0.35
            if field and field in hinted_fields:
                score += 2.5
            if vec_score < 0.15 and hit_tokens == 0 and q_lower not in blob:
                continue
        else:
            if hit_tokens == 0 and q_lower not in blob:
                continue
            score = kw

        scored.append(
            (
                score,
                {
                    "chunkId": int(r["id"]),
                    "documentId": int(r["document_id"]),
                    "collectionId": int(r["collection_id"]),
                    "collectionName": r["collection_name"] or "",
                    "documentTitle": title,
                    "ordinal": int(r["ordinal"]),
                    "text": text,
                    "meta": {
                        k: v
                        for k, v in meta.items()
                        if k != "embedding"  # 不回传大向量
                    },
                    "score": round(score, 4),
                    "keywordScore": round(kw, 3),
                    "vectorScore": round(vec_score, 4) if q_vec else None,
                },
            )
        )

    scored.sort(key=lambda x: (-x[0], x[1]["documentId"], x[1]["ordinal"]))
    hits = _ensure_structured_field_coverage(
        scored, top_k, _hinted_structured_fields(q)
    )
    # 刷新展示用 score 顺序（覆盖补入后按原 score 重排，便于阅读）
    hits.sort(
        key=lambda h: (
            -float(h.get("score") or 0),
            int(h.get("documentId") or 0),
            int(h.get("ordinal") or 0),
        )
    )
    _enrich_hits_with_attachment(hits)
    return {
        "query": q,
        "mode": mode,
        "topK": top_k,
        "collectionIds": cids,
        "totalCandidates": len(scored),
        "hits": hits,
        "referencedDocuments": referenced_documents_from_hits(hits),
        "embeddingConfigured": bool(creds),
        "chunksWithVectors": sum(
            1
            for r in rows
            if isinstance((r["meta"] if isinstance(r["meta"], dict) else {}).get("embedding"), list)
        ),
    }


_DEFAULT_ASK_SYSTEM = (
    "你是知识库问答助理。只能依据下方【知识库片段】回答用户问题。"
    "若片段不足以回答，请明确说明「根据当前知识库内容无法确定」，不要编造事实、数字或结论。"
    "用简洁的中文与 Markdown 列表/加粗组织回答。"
    "在关键事实处用 [1]、[2] 标注对应片段编号（编号与下方片段列表一致）；"
    "同一编号全文只出现一次（首次提到该片段时标注即可），不要在多句重复 [1][1][1]。"
)


def _format_knowledge(hits: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for i, h in enumerate(hits, start=1):
        title = h.get("documentTitle") or "未命名文档"
        coll = h.get("collectionName") or ""
        meta_title = ""
        meta = h.get("meta") if isinstance(h.get("meta"), dict) else {}
        if isinstance(meta.get("title"), str) and meta["title"].strip():
            meta_title = meta["title"].strip()
        head = f"[{i}] 《{title}》"
        if coll:
            head += f" · {coll}"
        if meta_title:
            head += f" · {meta_title}"
        text = (h.get("text") or "").strip()
        if len(text) > 1200:
            text = text[:1200] + "…"
        blocks.append(f"{head}\n{text}")
    return "\n\n".join(blocks)


def _fallback_answer_from_hits(
    query: str,
    hits: list[dict[str, Any]],
    empty: str,
) -> str:
    """Return a deterministic grounded answer when no LLM is configured."""
    if not hits:
        return empty
    lines = [
        "当前未配置默认 LLM，以下为基于知识库检索结果生成的摘录式回答：",
        "",
    ]
    for i, hit in enumerate(hits[:3], start=1):
        title = hit.get("documentTitle") or "未命名文档"
        text = " ".join(str(hit.get("text") or "").split())
        if len(text) > 360:
            text = text[:360].rstrip() + "..."
        lines.append(f"{i}. 《{title}》[{i}]：{text}")
    lines.extend(
        [
            "",
            f"问题：{query}",
            "说明：该回答未调用外部 LLM，仅用于返回可审计的知识库命中内容。",
        ]
    )
    return "\n".join(lines).strip()


def _ensure_collections_exist(collection_ids: list[int]) -> None:
    if not collection_ids:
        return
    wanted = {int(x) for x in collection_ids}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM kh_collections WHERE id = ANY(%s)",
            (list(wanted),),
        ).fetchall()
    found = {int(r["id"]) for r in rows}
    missing = sorted(wanted - found)
    if missing:
        raise KeyError("collection not found")


def get_chat(chat_id: int) -> dict[str, Any] | None:
    ensure_kh_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM kh_chats WHERE id = %s", (int(chat_id),)
        ).fetchone()
    if not row:
        return None
    return _chat_row(dict(row))


def ask(
    *,
    query: str,
    collection_ids: list[int] | None = None,
    chat_id: int | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """检索 + LLM 问答。无命中不调用模型；禁止无依据编造由提示词约束。"""
    from knowledge_hub.llm import KhLlmError, chat_completions, llm_configured

    q = (query or "").strip()
    if not q:
        raise ValueError("问题不能为空")

    chat: dict[str, Any] | None = None
    if chat_id is not None:
        chat = get_chat(int(chat_id))
        if not chat:
            raise KeyError("chat not found")

    cids = list(collection_ids or [])
    if not cids and chat:
        cids = list(chat.get("collectionIds") or [])
    if not cids:
        raise ValueError("请指定 collectionIds 或在聊天应用中关联知识库")
    _ensure_collections_exist(cids)

    retrieved = search_chunks(query=q, collection_ids=cids, top_k=top_k)
    hits = retrieved.get("hits") or []
    empty = (
        (chat.get("emptyResponse") if chat else "") or ""
    ).strip() or "知识库未找到与问题相关的内容。"

    if not hits:
        return {
            "query": q,
            "answer": empty,
            "grounded": False,
            "mode": retrieved.get("mode"),
            "topK": retrieved.get("topK"),
            "collectionIds": retrieved.get("collectionIds") or cids,
            "totalCandidates": retrieved.get("totalCandidates") or 0,
            "hits": [],
            "llmConfigured": llm_configured(),
            "model": None,
            "providerKey": None,
        }

    knowledge = _format_knowledge(hits)
    if not llm_configured():
        _enrich_hits_with_attachment(hits)
        return {
            "query": q,
            "answer": _fallback_answer_from_hits(q, hits, empty),
            "grounded": True,
            "mode": retrieved.get("mode"),
            "topK": retrieved.get("topK"),
            "collectionIds": retrieved.get("collectionIds") or cids,
            "totalCandidates": retrieved.get("totalCandidates") or 0,
            "hits": hits,
            "referencedDocuments": referenced_documents_from_hits(hits),
            "llmConfigured": False,
            "model": None,
            "providerKey": None,
            "degraded": True,
            "degradeReason": "llm_not_configured",
        }

    user_sys = ((chat.get("systemPrompt") if chat else "") or "").strip()
    if user_sys:
        if "{knowledge}" in user_sys:
            system = user_sys.replace("{knowledge}", knowledge)
        else:
            system = f"{user_sys}\n\n【知识库片段】\n{knowledge}"
    else:
        system = f"{_DEFAULT_ASK_SYSTEM}\n\n【知识库片段】\n{knowledge}"

    temp = chat.get("temperature") if chat else None
    top_p = chat.get("topP") if chat else None
    max_tok = chat.get("maxTokens") if chat else None
    model_override = (chat.get("modelName") if chat else None) or None

    llm_out = chat_completions(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": q},
        ],
        temperature=float(temp) if temp is not None else 0.2,
        max_tokens=int(max_tok) if max_tok is not None else 2048,
        top_p=float(top_p) if top_p is not None else None,
        model_override=str(model_override).strip() if model_override else None,
    )
    answer = (llm_out.get("content") or "").strip() or empty
    _enrich_hits_with_attachment(hits)
    return {
        "query": q,
        "answer": answer,
        "grounded": True,
        "mode": retrieved.get("mode"),
        "topK": retrieved.get("topK"),
        "collectionIds": retrieved.get("collectionIds") or cids,
        "totalCandidates": retrieved.get("totalCandidates") or 0,
        "hits": hits,
        "referencedDocuments": referenced_documents_from_hits(hits),
        "llmConfigured": True,
        "model": llm_out.get("model"),
        "providerKey": llm_out.get("providerKey"),
        "tokensIn": llm_out.get("tokensIn"),
        "tokensOut": llm_out.get("tokensOut"),
    }


def _chat_row(r: dict[str, Any]) -> dict[str, Any]:
    cids = r.get("collection_ids") or []
    if isinstance(cids, str):
        try:
            cids = json.loads(cids)
        except Exception:
            cids = []
    return {
        "id": int(r["id"]),
        "name": r["name"],
        "description": r.get("description") or "",
        "opener": r.get("opener") or "",
        "systemPrompt": r.get("system_prompt") or "",
        "emptyResponse": r.get("empty_response") or "",
        "collectionIds": [int(x) for x in cids],
        "modelName": r.get("model_name") or "",
        "temperature": r.get("temperature"),
        "topP": r.get("top_p"),
        "maxTokens": r.get("max_tokens"),
        "createdAt": _iso(r.get("created_at")),
        "updatedAt": _iso(r.get("updated_at")),
    }


def list_chats() -> list[dict[str, Any]]:
    ensure_kh_schema()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM kh_chats ORDER BY updated_at DESC"
        ).fetchall()
    return [_chat_row(dict(r)) for r in rows]


def create_chat(*, name: str, created_by: int | None = None) -> dict[str, Any]:
    ensure_kh_schema()
    title = (name or "").strip() or "未命名聊天"
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO kh_chats (name, created_by) VALUES (%s, %s) RETURNING *
            """,
            (title, created_by),
        ).fetchone()
        chat_id = int(row["id"])
        conn.execute(
            """
            INSERT INTO kh_conversations (chat_id, title)
            VALUES (%s, %s)
            """,
            (chat_id, "新会话"),
        )
    return _chat_row(dict(row))


def update_chat(chat_id: int, body: dict[str, Any]) -> dict[str, Any]:
    ensure_kh_schema()
    fields = []
    vals: list[Any] = []
    mapping = {
        "name": "name",
        "description": "description",
        "opener": "opener",
        "systemPrompt": "system_prompt",
        "emptyResponse": "empty_response",
        "modelName": "model_name",
    }
    for js, col in mapping.items():
        if js in body:
            fields.append(f"{col} = %s")
            vals.append(str(body.get(js) or ""))
    if "collectionIds" in body:
        fields.append("collection_ids = %s::jsonb")
        vals.append(json.dumps(body.get("collectionIds") or [], ensure_ascii=False))
    if "temperature" in body:
        fields.append("temperature = %s")
        vals.append(body.get("temperature"))
    if "topP" in body:
        fields.append("top_p = %s")
        vals.append(body.get("topP"))
    if "maxTokens" in body:
        fields.append("max_tokens = %s")
        vals.append(body.get("maxTokens"))
    if not fields:
        raise ValueError("无更新字段")
    fields.append("updated_at = NOW()")
    vals.append(int(chat_id))
    with get_conn() as conn:
        row = conn.execute(
            f"UPDATE kh_chats SET {', '.join(fields)} WHERE id = %s RETURNING *",
            tuple(vals),
        ).fetchone()
        if not row:
            raise KeyError("chat not found")
    return _chat_row(dict(row))


def delete_chat(chat_id: int) -> bool:
    ensure_kh_schema()
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM kh_chats WHERE id = %s RETURNING id", (int(chat_id),)
        )
        return bool(cur.fetchone())


def _conversation_row(r: dict[str, Any], *, message_count: int = 0) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "chatId": int(r["chat_id"]),
        "title": r.get("title") or "新会话",
        "messageCount": int(message_count),
        "createdAt": _iso(r.get("created_at")),
        "updatedAt": _iso(r.get("updated_at")),
    }


def list_conversations(chat_id: int) -> list[dict[str, Any]]:
    ensure_kh_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.*,
                   (SELECT COUNT(*) FROM kh_chat_messages m
                    WHERE m.conversation_id = c.id) AS message_count
            FROM kh_conversations c
            WHERE c.chat_id = %s
            ORDER BY c.updated_at DESC, c.id DESC
            """,
            (int(chat_id),),
        ).fetchall()
    return [
        _conversation_row(dict(r), message_count=int(r.get("message_count") or 0))
        for r in rows
    ]


def get_conversation(conversation_id: int) -> dict[str, Any] | None:
    ensure_kh_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT c.*,
                   (SELECT COUNT(*) FROM kh_chat_messages m
                    WHERE m.conversation_id = c.id) AS message_count
            FROM kh_conversations c
            WHERE c.id = %s
            """,
            (int(conversation_id),),
        ).fetchone()
    if not row:
        return None
    return _conversation_row(dict(row), message_count=int(row.get("message_count") or 0))


def create_conversation(chat_id: int, *, title: str | None = None) -> dict[str, Any]:
    ensure_kh_schema()
    title_s = (title or "").strip() or "新会话"
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id FROM kh_chats WHERE id = %s", (int(chat_id),)
        ).fetchone()
        if not exists:
            raise KeyError("chat not found")
        row = conn.execute(
            """
            INSERT INTO kh_conversations (chat_id, title)
            VALUES (%s, %s)
            RETURNING *
            """,
            (int(chat_id), title_s),
        ).fetchone()
        conn.execute(
            "UPDATE kh_chats SET updated_at = NOW() WHERE id = %s",
            (int(chat_id),),
        )
    return _conversation_row(dict(row), message_count=0)


def ensure_default_conversation(chat_id: int) -> dict[str, Any]:
    """旧 API / 迁移：保证聊天应用下至少有一个会话。"""
    ensure_kh_schema()
    items = list_conversations(chat_id)
    if items:
        # list 按 updated_at DESC；取最旧 id 作为「默认」不稳定，改取最早创建
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT c.*,
                       (SELECT COUNT(*) FROM kh_chat_messages m
                        WHERE m.conversation_id = c.id) AS message_count
                FROM kh_conversations c
                WHERE c.chat_id = %s
                ORDER BY c.id ASC
                LIMIT 1
                """,
                (int(chat_id),),
            ).fetchone()
        if row:
            return _conversation_row(
                dict(row), message_count=int(row.get("message_count") or 0)
            )
    return create_conversation(chat_id, title="默认会话")


def update_conversation(conversation_id: int, body: dict[str, Any]) -> dict[str, Any]:
    ensure_kh_schema()
    if "title" not in body:
        raise ValueError("无更新字段")
    title_s = str(body.get("title") or "").strip() or "新会话"
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE kh_conversations
            SET title = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (title_s, int(conversation_id)),
        ).fetchone()
        if not row:
            raise KeyError("conversation not found")
        conn.execute(
            "UPDATE kh_chats SET updated_at = NOW() WHERE id = %s",
            (int(row["chat_id"]),),
        )
        cnt = conn.execute(
            "SELECT COUNT(*) AS n FROM kh_chat_messages WHERE conversation_id = %s",
            (int(conversation_id),),
        ).fetchone()
    return _conversation_row(
        dict(row), message_count=int(cnt["n"] if cnt else 0)
    )


def delete_conversation(conversation_id: int) -> bool:
    ensure_kh_schema()
    with get_conn() as conn:
        row = conn.execute(
            "DELETE FROM kh_conversations WHERE id = %s RETURNING chat_id",
            (int(conversation_id),),
        ).fetchone()
        if not row:
            return False
        chat_id = int(row["chat_id"])
        # 删光后补一个空会话，避免助理下无会话可用
        left = conn.execute(
            "SELECT COUNT(*) AS n FROM kh_conversations WHERE chat_id = %s",
            (chat_id,),
        ).fetchone()
        if not left or int(left["n"] or 0) == 0:
            conn.execute(
                """
                INSERT INTO kh_conversations (chat_id, title)
                VALUES (%s, %s)
                """,
                (chat_id, "新会话"),
            )
        conn.execute(
            "UPDATE kh_chats SET updated_at = NOW() WHERE id = %s",
            (chat_id,),
        )
    return True


def _message_row(r: dict[str, Any]) -> dict[str, Any]:
    meta = r.get("meta")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    if not isinstance(meta, dict):
        meta = {}
    cid = r.get("conversation_id")
    return {
        "id": int(r["id"]),
        "chatId": int(r["chat_id"]),
        "conversationId": int(cid) if cid is not None else None,
        "role": str(r.get("role") or ""),
        "content": r.get("content") or "",
        "meta": meta,
        "createdAt": _iso(r.get("created_at")),
    }


def list_conversation_messages(
    conversation_id: int, *, limit: int = 200
) -> list[dict[str, Any]]:
    ensure_kh_schema()
    lim = max(1, min(int(limit or 200), 500))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM kh_chat_messages
            WHERE conversation_id = %s
            ORDER BY id ASC
            LIMIT %s
            """,
            (int(conversation_id), lim),
        ).fetchall()
    return [_message_row(dict(r)) for r in rows]


def append_conversation_message(
    conversation_id: int,
    *,
    role: str,
    content: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_kh_schema()
    role_s = (role or "").strip().lower()
    if role_s not in ("user", "assistant", "system"):
        raise ValueError("role 须为 user / assistant / system")
    with get_conn() as conn:
        conv = conn.execute(
            "SELECT id, chat_id FROM kh_conversations WHERE id = %s",
            (int(conversation_id),),
        ).fetchone()
        if not conv:
            raise KeyError("conversation not found")
        chat_id = int(conv["chat_id"])
        row = conn.execute(
            """
            INSERT INTO kh_chat_messages (chat_id, conversation_id, role, content, meta)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            RETURNING *
            """,
            (
                chat_id,
                int(conversation_id),
                role_s,
                content or "",
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        ).fetchone()
        # 用户首句自动当会话标题
        if role_s == "user" and (content or "").strip():
            title_row = conn.execute(
                "SELECT title FROM kh_conversations WHERE id = %s",
                (int(conversation_id),),
            ).fetchone()
            cur_title = (title_row["title"] if title_row else "") or ""
            if cur_title in ("", "新会话", "默认会话"):
                auto = (content or "").strip().replace("\n", " ")
                if len(auto) > 40:
                    auto = auto[:40] + "…"
                conn.execute(
                    """
                    UPDATE kh_conversations
                    SET title = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (auto, int(conversation_id)),
                )
            else:
                conn.execute(
                    "UPDATE kh_conversations SET updated_at = NOW() WHERE id = %s",
                    (int(conversation_id),),
                )
        else:
            conn.execute(
                "UPDATE kh_conversations SET updated_at = NOW() WHERE id = %s",
                (int(conversation_id),),
            )
        conn.execute(
            "UPDATE kh_chats SET updated_at = NOW() WHERE id = %s",
            (chat_id,),
        )
    return _message_row(dict(row))


def clear_conversation_messages(conversation_id: int) -> int:
    ensure_kh_schema()
    with get_conn() as conn:
        conv = conn.execute(
            "SELECT chat_id FROM kh_conversations WHERE id = %s",
            (int(conversation_id),),
        ).fetchone()
        if not conv:
            raise KeyError("conversation not found")
        cur = conn.execute(
            "DELETE FROM kh_chat_messages WHERE conversation_id = %s RETURNING id",
            (int(conversation_id),),
        )
        deleted = len(cur.fetchall())
        conn.execute(
            "UPDATE kh_conversations SET updated_at = NOW() WHERE id = %s",
            (int(conversation_id),),
        )
        conn.execute(
            "UPDATE kh_chats SET updated_at = NOW() WHERE id = %s",
            (int(conv["chat_id"]),),
        )
    return deleted


def list_chat_messages(chat_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
    """兼容旧路径：落到默认会话。"""
    conv = ensure_default_conversation(chat_id)
    return list_conversation_messages(int(conv["id"]), limit=limit)


def append_chat_message(
    chat_id: int,
    *,
    role: str,
    content: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """兼容旧路径：落到默认会话。"""
    conv = ensure_default_conversation(chat_id)
    return append_conversation_message(
        int(conv["id"]), role=role, content=content, meta=meta
    )


def clear_chat_messages(chat_id: int) -> int:
    """兼容旧路径：清空默认会话消息。"""
    conv = ensure_default_conversation(chat_id)
    return clear_conversation_messages(int(conv["id"]))


def list_files() -> list[dict[str, Any]]:
    ensure_kh_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT f.*, c.name AS collection_name
            FROM kh_files f
            LEFT JOIN kh_collections c ON c.id = f.collection_id
            ORDER BY f.created_at DESC
            """
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "title": r["title"],
            "fileName": r.get("file_name") or "",
            "fileSize": int(r.get("file_size") or 0),
            "collectionId": int(r["collection_id"]) if r.get("collection_id") else None,
            "collectionName": r.get("collection_name") or "",
            "createdAt": _iso(r.get("created_at")),
            "updatedAt": _iso(r.get("updated_at")),
        }
        for r in rows
    ]


def create_file(
    *,
    title: str,
    body: str = "",
    file_name: str = "",
    file_size: int = 0,
    collection_id: int | None = None,
    created_by: int | None = None,
) -> dict[str, Any]:
    ensure_kh_schema()
    title = (title or "").strip() or file_name or "未命名文件"
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO kh_files
              (title, file_name, file_size, body, collection_id, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                title,
                file_name or "",
                int(file_size or len(body or "")),
                body or "",
                collection_id,
                created_by,
            ),
        ).fetchone()
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "fileName": row.get("file_name") or "",
        "fileSize": int(row.get("file_size") or 0),
        "collectionId": int(row["collection_id"]) if row.get("collection_id") else None,
        "createdAt": _iso(row.get("created_at")),
    }


def delete_file(file_id: int) -> bool:
    ensure_kh_schema()
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM kh_files WHERE id = %s RETURNING id", (int(file_id),)
        )
        return bool(cur.fetchone())


def list_model_providers() -> list[dict[str, Any]]:
    ensure_kh_schema()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM kh_model_providers ORDER BY updated_at DESC"
        ).fetchall()
    out = []
    for r in rows:
        models = r.get("models") or []
        if isinstance(models, str):
            try:
                models = json.loads(models)
            except Exception:
                models = []
        out.append(
            {
                "id": int(r["id"]),
                "providerKey": r["provider_key"],
                "displayName": r["display_name"],
                "baseUrl": r.get("base_url") or "",
                "apiKeySet": bool((r.get("api_key") or "").strip()),
                "models": models,
                "updatedAt": _iso(r.get("updated_at")),
            }
        )
    return out


def upsert_model_provider(body: dict[str, Any]) -> dict[str, Any]:
    ensure_kh_schema()
    key = str(body.get("providerKey") or body.get("provider_key") or "").strip()
    if not key:
        raise ValueError("providerKey 不能为空")
    name = str(body.get("displayName") or body.get("display_name") or key).strip()
    base_url = str(body.get("baseUrl") or body.get("base_url") or "").strip()
    api_key = body.get("apiKey")
    if api_key is None:
        api_key = body.get("api_key")
    models = body.get("models") or []
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, api_key FROM kh_model_providers WHERE provider_key = %s",
            (key,),
        ).fetchone()
        if existing:
            new_key = (
                str(api_key)
                if api_key is not None and str(api_key).strip() != ""
                else (existing["api_key"] or "")
            )
            row = conn.execute(
                """
                UPDATE kh_model_providers
                SET display_name = %s, base_url = %s, api_key = %s,
                    models = %s::jsonb, updated_at = NOW()
                WHERE provider_key = %s
                RETURNING *
                """,
                (
                    name,
                    base_url,
                    new_key,
                    json.dumps(models, ensure_ascii=False),
                    key,
                ),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO kh_model_providers
                  (provider_key, display_name, base_url, api_key, models)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING *
                """,
                (
                    key,
                    name,
                    base_url,
                    str(api_key or ""),
                    json.dumps(models, ensure_ascii=False),
                ),
            ).fetchone()
    return {
        "id": int(row["id"]),
        "providerKey": row["provider_key"],
        "displayName": row["display_name"],
        "baseUrl": row.get("base_url") or "",
        "apiKeySet": bool((row.get("api_key") or "").strip()),
        "models": models,
    }


def delete_model_provider(provider_key: str) -> bool:
    ensure_kh_schema()
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM kh_model_providers WHERE provider_key = %s RETURNING id",
            (provider_key,),
        )
        return bool(cur.fetchone())


DEFAULT_MODEL_ROLES = ("llm", "embedding", "rerank", "vlm", "asr", "tts")


def get_default_models() -> dict[str, Any]:
    ensure_kh_schema()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM kh_default_models").fetchall()
    by = {r["role_key"]: dict(r) for r in rows}
    roles = {}
    for rk in DEFAULT_MODEL_ROLES:
        r = by.get(rk)
        roles[rk] = {
            "roleKey": rk,
            "providerKey": (r or {}).get("provider_key") or "",
            "modelName": (r or {}).get("model_name") or "",
            "enabled": rk in ("llm", "embedding", "rerank"),
        }
    return {"defaults": roles}


def set_default_models(body: dict[str, Any]) -> dict[str, Any]:
    ensure_kh_schema()
    defaults = body.get("defaults") or body
    with get_conn() as conn:
        for rk in DEFAULT_MODEL_ROLES:
            item = defaults.get(rk) or {}
            conn.execute(
                """
                INSERT INTO kh_default_models (role_key, provider_key, model_name, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (role_key) DO UPDATE SET
                  provider_key = EXCLUDED.provider_key,
                  model_name = EXCLUDED.model_name,
                  updated_at = NOW()
                """,
                (
                    rk,
                    str(item.get("providerKey") or item.get("provider_key") or ""),
                    str(item.get("modelName") or item.get("model_name") or ""),
                ),
            )
    return get_default_models()


def api_catalog() -> dict[str, Any]:
    """供 /settings/api 与 GET /api/kh/docs/outline：完成一个接口就在此追加一条。"""
    return {
        "title": "KnowledgeHub API",
        "version": "0.1.0",
        "baseUrl": "/api/kh",
        "auth": "Authorization: Bearer <SVQuant admin JWT>",
        "note": "问答必须基于检索片段，禁止无依据编造。完成一个接口就在本目录追加说明。",
        "endpoints": [
            {
                "id": "meta",
                "method": "GET",
                "path": "/api/kh/meta",
                "summary": "元数据：知识库类型与分块策略列表",
                "status": "ready",
                "request": None,
                "responseExample": {
                    "pipelines": [{"id": "general", "labelZh": "通用", "defaultChunk": "plain_window"}],
                    "chunkStrategies": [{"id": "markdown_heading", "labelZh": "按 Markdown 标题"}],
                },
            },
            {
                "id": "list-collections",
                "method": "GET",
                "path": "/api/kh/collections",
                "summary": "列出知识库",
                "status": "ready",
                "request": None,
                "responseExample": {
                    "collections": [
                        {
                            "id": 1,
                            "name": "示例库",
                            "pipeline": "general",
                            "chunkStrategy": "markdown_heading",
                            "documentCount": 2,
                        }
                    ]
                },
            },
            {
                "id": "create-collection",
                "method": "POST",
                "path": "/api/kh/collections",
                "summary": "创建知识库",
                "status": "ready",
                "request": {
                    "name": "因子手册",
                    "pipeline": "general",
                    "chunkStrategy": "markdown_heading",
                },
                "responseExample": {"collection": {"id": 4, "name": "因子手册"}},
            },
            {
                "id": "update-collection",
                "method": "PUT",
                "path": "/api/kh/collections/{id}",
                "summary": "重命名 / 更新知识库",
                "status": "ready",
                "request": {"name": "新名称", "description": "可选"},
                "responseExample": {"collection": {"id": 4, "name": "新名称"}},
            },
            {
                "id": "delete-collection",
                "method": "DELETE",
                "path": "/api/kh/collections/{id}",
                "summary": "删除知识库（级联文档与切片）",
                "status": "ready",
                "request": None,
                "responseExample": {"ok": True},
            },
            {
                "id": "list-documents",
                "method": "GET",
                "path": "/api/kh/collections/{id}/documents",
                "summary": "列出知识库内文档",
                "status": "ready",
                "request": None,
                "responseExample": {
                    "documents": [
                        {"id": 1, "title": "因子库总览", "status": "ready", "chunkCount": 149}
                    ]
                },
            },
            {
                "id": "create-document",
                "method": "POST",
                "path": "/api/kh/documents",
                "summary": "上传/粘贴文档并可选立即解析（docx/pdf 传 contentBase64）",
                "status": "ready",
                "request": {
                    "collectionId": 4,
                    "title": "因子库总览",
                    "body": "# ... markdown ...",
                    "fileName": "因子库总览.md",
                    "ingest": True,
                },
                "responseExample": {"document": {"id": 2, "status": "ready", "chunkCount": 149}},
            },
            {
                "id": "create-document-binary",
                "method": "POST",
                "path": "/api/kh/documents",
                "summary": "上传 Word/PDF：contentBase64 + fileName（.docx/.pdf），服务端抽文本",
                "status": "ready",
                "request": {
                    "collectionId": 4,
                    "title": "研报摘录",
                    "fileName": "note.docx",
                    "contentBase64": "<base64…>",
                    "ingest": True,
                },
                "responseExample": {"document": {"id": 3, "status": "ready", "sourceType": "docx"}},
            },
            {
                "id": "update-document",
                "method": "PUT",
                "path": "/api/kh/documents/{id}",
                "summary": "重命名 / 启用停用（enabled）等",
                "status": "ready",
                "request": {"title": "新标题", "enabled": True},
                "responseExample": {
                    "document": {"id": 2, "title": "新标题", "enabled": True},
                },
            },
            {
                "id": "delete-document",
                "method": "DELETE",
                "path": "/api/kh/documents/{id}",
                "summary": "删除文档及切片",
                "status": "ready",
                "request": None,
                "responseExample": {"ok": True},
            },
            {
                "id": "get-document",
                "method": "GET",
                "path": "/api/kh/documents/{id}",
                "summary": "文档详情（含正文）",
                "status": "ready",
                "request": None,
                "responseExample": {"document": {"id": 2, "title": "…", "body": "…", "chunkCount": 149}},
            },
            {
                "id": "list-chunks",
                "method": "GET",
                "path": "/api/kh/documents/{id}/chunks",
                "summary": "文档切片列表",
                "status": "ready",
                "request": None,
                "responseExample": {
                    "chunks": [{"id": 1, "ordinal": 0, "text": "…", "meta": {"title": "alpha101"}}]
                },
            },
            {
                "id": "ingest-document",
                "method": "POST",
                "path": "/api/kh/documents/{id}/ingest",
                "summary": "对已有文档重新分块解析",
                "status": "ready",
                "request": {},
                "responseExample": {"documentId": 2, "status": "ready", "chunkCount": 149},
            },
            {
                "id": "search",
                "method": "POST",
                "path": "/api/kh/search",
                "summary": "检索切片（Embedding→hybrid，否则关键词；仅 ready+enabled）",
                "status": "ready",
                "request": {
                    "query": "alpha101",
                    "collectionId": 4,
                    "collectionIds": [4],
                    "topK": 8,
                },
                "responseExample": {
                    "mode": "keyword",
                    "totalCandidates": 1,
                    "hits": [
                        {
                            "chunkId": 12,
                            "documentTitle": "因子库总览",
                            "ordinal": 1,
                            "score": 6.8,
                            "text": "### `alpha101` …",
                        }
                    ],
                },
            },
            {
                "id": "list-chat-messages",
                "method": "GET",
                "path": "/api/kh/chats/{id}/messages",
                "summary": "（兼容）默认会话的历史消息",
                "status": "ready",
                "request": None,
                "responseExample": {
                    "messages": [
                        {"id": 1, "role": "user", "content": "alpha101", "meta": {}}
                    ]
                },
            },
            {
                "id": "list-conversations",
                "method": "GET",
                "path": "/api/kh/chats/{id}/conversations",
                "summary": "聊天应用下的会话列表",
                "status": "ready",
                "request": None,
                "responseExample": {
                    "conversations": [
                        {"id": 1, "chatId": 1, "title": "alpha101", "messageCount": 2}
                    ]
                },
            },
            {
                "id": "create-conversation",
                "method": "POST",
                "path": "/api/kh/chats/{id}/conversations",
                "summary": "新建会话",
                "status": "ready",
                "request": {"title": "新会话"},
                "responseExample": {"conversation": {"id": 2, "title": "新会话"}},
            },
            {
                "id": "update-conversation",
                "method": "PUT",
                "path": "/api/kh/conversations/{id}",
                "summary": "重命名会话",
                "status": "ready",
                "request": {"title": "新标题"},
                "responseExample": {"conversation": {"id": 2, "title": "新标题"}},
            },
            {
                "id": "delete-conversation",
                "method": "DELETE",
                "path": "/api/kh/conversations/{id}",
                "summary": "删除会话（级联消息；若删光会补一个空会话）",
                "status": "ready",
                "request": None,
                "responseExample": {"ok": True},
            },
            {
                "id": "list-conversation-messages",
                "method": "GET",
                "path": "/api/kh/conversations/{id}/messages",
                "summary": "会话历史（检索预览写在 assistant.meta）",
                "status": "ready",
                "request": None,
                "responseExample": {
                    "messages": [
                        {"id": 1, "role": "user", "content": "alpha101", "meta": {}},
                        {
                            "id": 2,
                            "role": "assistant",
                            "content": "",
                            "meta": {"kind": "retrieval", "mode": "hybrid", "hits": []},
                        },
                    ]
                },
            },
            {
                "id": "append-conversation-message",
                "method": "POST",
                "path": "/api/kh/conversations/{id}/messages",
                "summary": "追加一条会话消息",
                "status": "ready",
                "request": {"role": "user", "content": "alpha101", "meta": {}},
                "responseExample": {"message": {"id": 1, "role": "user", "content": "alpha101"}},
            },
            {
                "id": "clear-conversation-messages",
                "method": "DELETE",
                "path": "/api/kh/conversations/{id}/messages",
                "summary": "清空该会话历史",
                "status": "ready",
                "request": None,
                "responseExample": {"ok": True, "deleted": 2},
            },
            {
                "id": "append-chat-message",
                "method": "POST",
                "path": "/api/kh/chats/{id}/messages",
                "summary": "（兼容）追加到默认会话",
                "status": "ready",
                "request": {
                    "role": "user",
                    "content": "alpha101",
                    "meta": {},
                },
                "responseExample": {"message": {"id": 1, "role": "user", "content": "alpha101"}},
            },
            {
                "id": "clear-chat-messages",
                "method": "DELETE",
                "path": "/api/kh/chats/{id}/messages",
                "summary": "（兼容）清空默认会话历史",
                "status": "ready",
                "request": None,
                "responseExample": {"ok": True, "deleted": 2},
            },
            {
                "id": "ask",
                "method": "POST",
                "path": "/api/kh/ask",
                "summary": "基于检索的问答（须引用片段；无命中不调 LLM；仅 ready+enabled）",
                "status": "ready",
                "request": {
                    "query": "alpha101 是什么",
                    "chatId": 1,
                    "collectionIds": [4],
                    "topK": 5,
                },
                "responseExample": {
                    "answer": "…",
                    "grounded": True,
                    "mode": "hybrid",
                    "hits": [{"chunkId": 12, "documentTitle": "因子库总览"}],
                },
            },
            {
                "id": "create-structured-document",
                "method": "POST",
                "path": "/api/kh/documents/structured",
                "summary": "Create a structured document from extracted sections.",
                "status": "ready",
                "request": {"title": "Factor notes", "sections": [{"title": "Intro", "content": "alpha101"}]},
                "responseExample": {"document": {"id": 1, "title": "Factor notes"}},
            },
            {
                "id": "get-document-attachment",
                "method": "GET",
                "path": "/api/kh/documents/{id}/attachment",
                "summary": "Download the original uploaded attachment for a document.",
                "status": "ready",
                "request": None,
                "responseExample": {"contentType": "application/pdf", "filename": "factor.pdf"},
            },
            {
                "id": "get-document-progress",
                "method": "GET",
                "path": "/api/kh/documents/{id}/progress",
                "summary": "Read the indexing/progress state for a document.",
                "status": "ready",
                "request": None,
                "responseExample": {"documentId": 1, "status": "ready", "progress": 100},
            },
            {
                "id": "list-chats",
                "method": "GET",
                "path": "/api/kh/chats",
                "summary": "List chat workspaces.",
                "status": "ready",
                "request": None,
                "responseExample": {"chats": [{"id": 1, "title": "Default"}]},
            },
            {
                "id": "create-chat",
                "method": "POST",
                "path": "/api/kh/chats",
                "summary": "Create a chat workspace.",
                "status": "ready",
                "request": {"title": "New chat"},
                "responseExample": {"chat": {"id": 1, "title": "New chat"}},
            },
            {
                "id": "update-chat",
                "method": "PUT",
                "path": "/api/kh/chats/{id}",
                "summary": "Rename or update a chat workspace.",
                "status": "ready",
                "request": {"title": "Renamed chat"},
                "responseExample": {"chat": {"id": 1, "title": "Renamed chat"}},
            },
            {
                "id": "delete-chat",
                "method": "DELETE",
                "path": "/api/kh/chats/{id}",
                "summary": "Delete a chat workspace.",
                "status": "ready",
                "request": None,
                "responseExample": {"ok": True},
            },
            {
                "id": "list-files",
                "method": "GET",
                "path": "/api/kh/files",
                "summary": "List files managed by KnowledgeHub.",
                "status": "ready",
                "request": None,
                "responseExample": {"files": [{"id": 1, "name": "factor.pdf"}]},
            },
            {
                "id": "upload-file",
                "method": "POST",
                "path": "/api/kh/files",
                "summary": "Upload a file for KnowledgeHub ingestion.",
                "status": "ready",
                "request": {"file": "<multipart file>"},
                "responseExample": {"file": {"id": 1, "name": "factor.pdf"}},
            },
            {
                "id": "delete-file",
                "method": "DELETE",
                "path": "/api/kh/files/{id}",
                "summary": "Delete a KnowledgeHub file.",
                "status": "ready",
                "request": None,
                "responseExample": {"ok": True},
            },
            {
                "id": "list-model-providers",
                "method": "GET",
                "path": "/api/kh/model-providers",
                "summary": "List configured model providers.",
                "status": "ready",
                "request": None,
                "responseExample": {"providers": [{"id": 1, "name": "default", "enabled": True}]},
            },
            {
                "id": "create-model-provider",
                "method": "POST",
                "path": "/api/kh/model-providers",
                "summary": "Create or register a model provider.",
                "status": "ready",
                "request": {"name": "default", "baseUrl": "https://example.invalid", "apiKey": "***"},
                "responseExample": {"provider": {"id": 1, "name": "default", "enabled": True}},
            },
            {
                "id": "delete-model-provider",
                "method": "DELETE",
                "path": "/api/kh/model-providers/{id}",
                "summary": "Delete a model provider.",
                "status": "ready",
                "request": None,
                "responseExample": {"ok": True},
            },
            {
                "id": "test-model-provider",
                "method": "POST",
                "path": "/api/kh/model-providers/test",
                "summary": "Test model provider connectivity.",
                "status": "ready",
                "request": {"providerId": 1},
                "responseExample": {"ok": True, "latencyMs": 120},
            },
            {
                "id": "get-default-models",
                "method": "GET",
                "path": "/api/kh/default-models",
                "summary": "Read KnowledgeHub default model selections.",
                "status": "ready",
                "request": None,
                "responseExample": {"chat": "gpt-4.1-mini", "embedding": "text-embedding-3-small"},
            },
            {
                "id": "save-default-models",
                "method": "POST",
                "path": "/api/kh/default-models",
                "summary": "Save KnowledgeHub default model selections.",
                "status": "ready",
                "request": {"chat": "gpt-4.1-mini", "embedding": "text-embedding-3-small"},
                "responseExample": {"ok": True},
            },
            {
                "id": "update-default-models",
                "method": "PUT",
                "path": "/api/kh/default-models",
                "summary": "Update KnowledgeHub default model selections.",
                "status": "ready",
                "request": {"chat": "gpt-4.1-mini"},
                "responseExample": {"ok": True},
            },
            {
                "id": "get-docs-outline",
                "method": "GET",
                "path": "/api/kh/docs/outline",
                "summary": "Read KnowledgeHub API documentation outline.",
                "status": "ready",
                "request": None,
                "responseExample": {"groups": [{"title": "KnowledgeHub API", "items": []}]},
            },
        ],
    }
