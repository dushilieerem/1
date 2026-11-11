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


# 登记表必须显式限定 schema：连接池的 search_path 是 "$user", public，而生产库的
# 角色名和 schema 名都叫 svquant。迁移 0036 会在 apply 过程中 CREATE SCHEMA svquant，
# 一旦 schema 出现，未限定的 schema_migrations 就从 public 翻到 svquant：写进 public、
# 读却是空的 svquant，空库门禁因此报「全部 pending」（2026-11-11 CI 变红即此因）。
REGISTRY_CANDIDATES = ("svquant", "public")


def _pick_registry_schema(conn) -> str:
    """选定登记表所在 schema：已有登记行的表优先（生产在 svquant），否则 public。

    选定后本次调用的所有语句都用限定名，避免中途建 schema 导致解析翻转。
    """
    counts: dict[str, int] = {}
    for schema in REGISTRY_CANDIDATES:
        exists = conn.execute(
            "SELECT to_regclass(%s) IS NOT NULL AS ok", (f"{schema}.schema_migrations",)
        ).fetchone()["ok"]
        if exists:
            counts[schema] = int(
                conn.execute(f"SELECT COUNT(*) AS n FROM {schema}.schema_migrations").fetchone()["n"]
            )
    if not counts:
        return "public"
    non_empty = {s: n for s, n in counts.items() if n}
    pool = non_empty or counts
    return max(pool, key=lambda s: (pool[s], -REGISTRY_CANDIDATES.index(s)))


def _ensure_table(conn) -> str:
    schema = _pick_registry_schema(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {schema}.schema_migrations (
          version    TEXT PRIMARY KEY,
          checksum   TEXT NOT NULL,
          applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    return schema


def _applied(conn, schema: str) -> dict[str, str]:
    rows = conn.execute(f"SELECT version, checksum FROM {schema}.schema_migrations").fetchall()
    return {str(r["version"]): str(r["checksum"]) for r in rows}


def status() -> dict[str, Any]:
    with get_conn() as conn:
        schema = _ensure_table(conn)
        applied = _applied(conn, schema)
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
        schema = _ensure_table(conn)
        applied = _applied(conn, schema)
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
                    f"INSERT INTO {schema}.schema_migrations (version, checksum) VALUES (%s, %s)",
                    (version, checksum),
                )
            applied_now.append(version)
    return {"ok": True, "applied_now": applied_now, "registry_schema": schema, **status()}


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
