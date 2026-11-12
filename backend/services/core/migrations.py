# -*- coding: utf-8 -*-
"""版本化 SQL 迁移（P0-10）。

不做 ORM autogenerate：现有 schema 仍由各 ensure_*_schema 创建，0001 是基线；
后续增量变更写 `migrations/NNNN_*.sql`，由本模块按序执行并记录 checksum。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from services.core.db import get_conn

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _files() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        return []
    return sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.is_file())


def _ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version    TEXT PRIMARY KEY,
          checksum   TEXT NOT NULL,
          applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _applied(conn) -> dict[str, str]:
    rows = conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
    return {str(r["version"]): str(r["checksum"]) for r in rows}


def status() -> dict[str, Any]:
    with get_conn() as conn:
        _ensure_table(conn)
        applied = _applied(conn)
    files = _files()
    pending = []
    for path in files:
        version = path.stem
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if version not in applied:
            pending.append({"version": version, "path": str(path)})
        elif applied[version] != checksum:
            pending.append({"version": version, "path": str(path), "changed": True})
    return {
        "ok": not pending,
        "current": max(applied) if applied else None,
        "applied": sorted(applied),
        "pending": pending,
        "head": files[-1].stem if files else None,
    }


def apply_migrations() -> dict[str, Any]:
    applied_now: list[str] = []
    with get_conn() as conn:
        _ensure_table(conn)
        applied = _applied(conn)
        for path in _files():
            version = path.stem
            raw = path.read_bytes()
            checksum = hashlib.sha256(raw).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(f"迁移 {version} 已执行但文件内容已变化，请新增迁移而不是修改历史")
                continue
            sql = raw.decode("utf-8")
            # 每个文件一个事务；psycopg 的 execute 可执行多语句脚本。
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                    (version, checksum),
                )
            applied_now.append(version)
    return {"ok": True, "applied": applied_now, **status()}


def _main() -> None:
    import json
    import sys

    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    elif action == "apply":
        print(json.dumps(apply_migrations(), ensure_ascii=False, indent=2))
    else:
        raise SystemExit("用法: python -m services.core.migrations [status|apply]")


if __name__ == "__main__":
    _main()


__all__ = ["apply_migrations", "status"]
