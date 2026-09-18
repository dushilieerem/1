# -*- coding: utf-8 -*-
"""知识库文档附件：落盘 + 元数据。"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

from services.core.db import get_conn

_ATTACHMENT_ROOT: Path | None = None


def attachment_root() -> Path:
    global _ATTACHMENT_ROOT
    if _ATTACHMENT_ROOT is not None:
        return _ATTACHMENT_ROOT
    env = (os.environ.get("KH_ATTACHMENT_DIR") or "").strip()
    if env:
        root = Path(env)
    else:
        # .../SVQuant/KnowledgeHub/data/kh_attachments
        root = Path(__file__).resolve().parents[2] / "data" / "kh_attachments"
    root.mkdir(parents=True, exist_ok=True)
    _ATTACHMENT_ROOT = root
    return root


def _safe_name(name: str) -> str:
    base = Path(name or "attachment").name
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base)
    return base or "attachment"


def save_attachment_bytes(data: bytes, file_name: str) -> dict[str, Any]:
    from knowledge_hub.store import ensure_kh_schema

    ensure_kh_schema()
    if not data:
        raise ValueError("附件内容为空")
    fname = _safe_name(file_name)
    digest = hashlib.sha256(data).hexdigest()
    sub = digest[:2]
    dest_dir = attachment_root() / sub
    dest_dir.mkdir(parents=True, exist_ok=True)
    storage_name = f"{digest}_{fname}"
    path = dest_dir / storage_name
    if not path.exists():
        path.write_bytes(data)
    mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    rel = f"{sub}/{storage_name}"
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO kh_attachments
              (file_name, mime_type, size_bytes, storage_path, sha256)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (fname, mime, len(data), rel, digest),
        ).fetchone()
    return _attachment_row(dict(row))


def read_attachment(attachment_id: int) -> tuple[bytes, str, str]:
    from knowledge_hub.store import ensure_kh_schema

    ensure_kh_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM kh_attachments WHERE id = %s", (int(attachment_id),)
        ).fetchone()
    if not row:
        raise FileNotFoundError("附件不存在")
    rel = row["storage_path"] or ""
    path = attachment_root() / rel
    if not path.is_file():
        raise FileNotFoundError("附件文件已丢失")
    return path.read_bytes(), row["file_name"] or "attachment", row["mime_type"] or "application/octet-stream"


def delete_attachment(attachment_id: int) -> None:
    from knowledge_hub.store import ensure_kh_schema

    ensure_kh_schema()
    with get_conn() as conn:
        row = conn.execute(
            "DELETE FROM kh_attachments WHERE id = %s RETURNING storage_path",
            (int(attachment_id),),
        ).fetchone()
    if not row:
        return
    rel = row["storage_path"] or ""
    path = attachment_root() / rel
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _attachment_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "fileName": r.get("file_name") or "",
        "mimeType": r.get("mime_type") or "",
        "sizeBytes": int(r.get("size_bytes") or 0),
    }


def attachment_info(attachment_id: int | None) -> dict[str, Any] | None:
    if not attachment_id:
        return None
    from knowledge_hub.store import ensure_kh_schema

    ensure_kh_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, file_name, mime_type, size_bytes FROM kh_attachments WHERE id = %s",
            (int(attachment_id),),
        ).fetchone()
    if not row:
        return None
    return _attachment_row(dict(row))
