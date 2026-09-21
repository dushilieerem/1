# -*- coding: utf-8 -*-
"""因子面板校验状态：产品事实存储于 PostgreSQL。"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.core.db import get_conn


VERIFY_STATUSES = frozenset({"pending", "passed", "failed"})
LEGACY_LIBRARY_NAME = "*"
LEGACY_MIGRATION_KEY = "factor_dashboard_verifications_from_sqlite_v1"
LEGACY_SQLITE_PATH = (
    Path(__file__).resolve().parents[2]
    / "output"
    / "factor_dashboard"
    / "metrics.sqlite"
)

_migration_lock = threading.Lock()
_legacy_migration_done = False


def ensure_factor_verification_schema() -> None:
    """创建校验状态表；状态是产品数据，与指标缓存分开。"""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factor_dashboard_verifications (
              library_name TEXT NOT NULL,
              factor_name  TEXT NOT NULL,
              status       TEXT NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'passed', 'failed')),
              note         TEXT NOT NULL DEFAULT '',
              updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_by   TEXT NOT NULL DEFAULT '',
              PRIMARY KEY (library_name, factor_name)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_factor_dashboard_verifications_name
            ON factor_dashboard_verifications (factor_name)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factor_dashboard_legacy_imports (
              migration_key TEXT PRIMARY KEY,
              source_rows BIGINT NOT NULL DEFAULT 0,
              imported_rows BIGINT NOT NULL DEFAULT 0,
              skipped_rows BIGINT NOT NULL DEFAULT 0,
              completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def _parse_legacy_timestamp(raw: Any) -> datetime:
    value = str(raw or "").strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _read_legacy_rows() -> list[dict[str, Any]] | None:
    """只读读取旧面板 SQLite；不会创建或修改旧文件。"""
    if not LEGACY_SQLITE_PATH.is_file():
        return None

    uri = f"file:{LEGACY_SQLITE_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            ("factor_verify_status",),
        ).fetchone()
        if table is None:
            return None
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(factor_verify_status)")
        }
        required = {"factor_name", "status", "note", "updated_at", "updated_by"}
        if not required.issubset(columns):
            raise RuntimeError("旧因子校验表字段不完整，已停止迁移以避免丢失记录")
        rows = conn.execute(
            """
            SELECT factor_name, status, note, updated_at, updated_by
            FROM factor_verify_status
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def migrate_legacy_factor_verifications() -> dict[str, int]:
    """幂等导入旧 SQLite 校验记录，保留旧状态的全库因子名语义。

    旧表没有 library_name，因此导入为 ``library_name='*'``。面板读取时，
    精确库名记录优先；没有精确记录时才回退到该兼容记录。
    """
    global _legacy_migration_done
    if _legacy_migration_done:
        return {"source_rows": 0, "imported_rows": 0, "skipped_rows": 0}

    with _migration_lock:
        if _legacy_migration_done:
            return {"source_rows": 0, "imported_rows": 0, "skipped_rows": 0}
        ensure_factor_verification_schema()
        with get_conn() as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (LEGACY_MIGRATION_KEY,),
            )
            marker = conn.execute(
                """
                SELECT 1
                FROM factor_dashboard_legacy_imports
                WHERE migration_key = %s
                """,
                (LEGACY_MIGRATION_KEY,),
            ).fetchone()
            result = (
                {"source_rows": 0, "imported_rows": 0, "skipped_rows": 0}
                if marker is not None
                else _import_legacy_factor_verifications(conn)
            )

        _legacy_migration_done = True
        return result


def _import_legacy_factor_verifications(conn: Any) -> dict[str, int]:
    rows = _read_legacy_rows()
    if rows is None:
        return {"source_rows": 0, "imported_rows": 0, "skipped_rows": 0}

    imported = 0
    skipped = 0
    for row in rows:
        factor_name = str(row.get("factor_name") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        if not factor_name or status not in VERIFY_STATUSES:
            skipped += 1
            continue

        cursor = conn.execute(
            """
            INSERT INTO factor_dashboard_verifications
              (library_name, factor_name, status, note, updated_at, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (library_name, factor_name) DO UPDATE SET
              status = EXCLUDED.status,
              note = EXCLUDED.note,
              updated_at = EXCLUDED.updated_at,
              updated_by = EXCLUDED.updated_by
            WHERE factor_dashboard_verifications.updated_at < EXCLUDED.updated_at
            RETURNING factor_name
            """,
            (
                LEGACY_LIBRARY_NAME,
                factor_name,
                status,
                str(row.get("note") or ""),
                _parse_legacy_timestamp(row.get("updated_at")),
                str(row.get("updated_by") or ""),
            ),
        )
        if cursor.fetchone() is not None:
            imported += 1
    conn.execute(
        """
        INSERT INTO factor_dashboard_legacy_imports
          (migration_key, source_rows, imported_rows, skipped_rows)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (migration_key) DO NOTHING
        """,
        (LEGACY_MIGRATION_KEY, len(rows), imported, skipped),
    )
    return {
        "source_rows": len(rows),
        "imported_rows": imported,
        "skipped_rows": skipped,
    }


def list_factor_verification_map() -> dict[tuple[str, str], dict[str, str]]:
    migrate_legacy_factor_verifications()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT library_name, factor_name, status, note, updated_at, updated_by
            FROM factor_dashboard_verifications
            """
        ).fetchall()

    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (str(row["library_name"]), str(row["factor_name"]))
        updated_at = row["updated_at"]
        result[key] = {
            "status": str(row["status"] or "pending"),
            "note": str(row["note"] or ""),
            "updated_at": updated_at.isoformat() if updated_at else "",
            "updated_by": str(row["updated_by"] or ""),
        }
    return result


def set_factor_verification_status(
    *,
    factor_name: str,
    status: str,
    library_name: str | None = None,
    note: str = "",
    updated_by: str = "",
) -> dict[str, Any]:
    name = (factor_name or "").strip()
    st = (status or "").strip().lower()
    library = (library_name or "").strip()
    if not name:
        raise ValueError("factor_name 不能为空")
    if st not in VERIFY_STATUSES:
        raise ValueError("status 须为 pending / passed / failed")

    # 延迟导入避免 dashboard_store 与此存储模块形成导入环。
    from services.factor.dashboard_store import load_factor_index

    catalog = load_factor_index(include_qlib=True)
    if library:
        valid = any(
            item.get("name") == name and item.get("library") == library
            for item in catalog
        )
        if not valid:
            raise ValueError(f"因子不在官方面板目录：{library}/{name}")
    else:
        if not any(item.get("name") == name for item in catalog):
            raise ValueError(f"因子不在官方面板目录：{name}")
        # 兼容旧客户端：未传库名时保留旧的全局因子名状态。
        library = LEGACY_LIBRARY_NAME

    migrate_legacy_factor_verifications()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO factor_dashboard_verifications
              (library_name, factor_name, status, note, updated_at, updated_by)
            VALUES (%s, %s, %s, %s, NOW(), %s)
            ON CONFLICT (library_name, factor_name) DO UPDATE SET
              status = EXCLUDED.status,
              note = EXCLUDED.note,
              updated_at = EXCLUDED.updated_at,
              updated_by = EXCLUDED.updated_by
            RETURNING library_name, factor_name, status, note, updated_at, updated_by
            """,
            (library, name, st, str(note or ""), str(updated_by or "")),
        ).fetchone()

    updated_at = row["updated_at"]
    return {
        "ok": True,
        "library_name": str(row["library_name"]),
        "factor_name": str(row["factor_name"]),
        "verify_status": str(row["status"]),
        "verify_note": str(row["note"] or ""),
        "verify_updated_at": updated_at.isoformat() if updated_at else "",
        "verify_updated_by": str(row["updated_by"] or ""),
    }


__all__ = [
    "LEGACY_LIBRARY_NAME",
    "VERIFY_STATUSES",
    "ensure_factor_verification_schema",
    "list_factor_verification_map",
    "migrate_legacy_factor_verifications",
    "set_factor_verification_status",
]
