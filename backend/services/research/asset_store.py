# -*- coding: utf-8 -*-
"""用户研究资产：静态证券池与固定权重组合基准（FEAT-018）。

版本化规则：每次成分/权重变化写一个新快照；旧版本不可变。
ResearchEngine 只消费快照，不读取本库。
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from services.core.db import get_conn

SYMBOL_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")


def ensure_asset_schema() -> None:
    from services.billing.billing_store import ensure_billing_schema

    ensure_billing_schema()
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_universes (
              id              BIGSERIAL PRIMARY KEY,
              user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name            TEXT NOT NULL,
              description     TEXT NOT NULL DEFAULT '',
              current_version INTEGER NOT NULL DEFAULT 1,
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (user_id, name)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_universe_versions (
              id            BIGSERIAL PRIMARY KEY,
              universe_id   BIGINT NOT NULL REFERENCES user_universes(id) ON DELETE CASCADE,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              version_no    INTEGER NOT NULL,
              symbols       JSONB NOT NULL,
              content_hash  TEXT NOT NULL,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (universe_id, version_no)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_benchmarks (
              id              BIGSERIAL PRIMARY KEY,
              user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name            TEXT NOT NULL,
              description     TEXT NOT NULL DEFAULT '',
              current_version INTEGER NOT NULL DEFAULT 1,
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (user_id, name)
            )
            """
        )
        for table in ("user_universes", "user_benchmarks"):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS org_id BIGINT "
                "REFERENCES app_orgs(id) ON DELETE SET NULL"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_benchmark_versions (
              id            BIGSERIAL PRIMARY KEY,
              benchmark_id  BIGINT NOT NULL REFERENCES user_benchmarks(id) ON DELETE CASCADE,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              version_no    INTEGER NOT NULL,
              weights       JSONB NOT NULL,
              content_hash  TEXT NOT NULL,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (benchmark_id, version_no)
            )
            """
        )


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _clean_symbols(symbols: list[str]) -> list[str]:
    out: list[str] = []
    for raw in symbols or []:
        sym = str(raw or "").strip().upper()
        if not SYMBOL_RE.match(sym):
            raise ValueError(f"证券代码格式错误: {raw}")
        if sym not in out:
            out.append(sym)
    if not out:
        raise ValueError("证券池不能为空")
    if len(out) > 500:
        raise ValueError("证券池最多 500 只")
    return sorted(out)


def _clean_weights(weights: Any) -> dict[str, float]:
    items: list[tuple[str, float]]
    if isinstance(weights, dict):
        items = [(str(k), float(v)) for k, v in weights.items()]
    elif isinstance(weights, list):
        items = [(str(x.get("symbol")), float(x.get("weight"))) for x in weights if isinstance(x, dict)]
    else:
        raise ValueError("weights 必须是对象或数组")
    out: dict[str, float] = {}
    for sym, weight in items:
        key = sym.strip().upper()
        if not SYMBOL_RE.match(key):
            raise ValueError(f"证券代码格式错误: {sym}")
        if weight < 0:
            raise ValueError("权重不能为负")
        out[key] = out.get(key, 0.0) + weight
    if not out:
        raise ValueError("基准不能为空")
    total = sum(out.values())
    if abs(total - 1.0) > 1e-4:
        raise ValueError(f"权重之和必须为 1（当前 {total:.6f}）")
    return {k: round(v, 10) for k, v in sorted(out.items())}


def _org_member(conn, org_id: int | None, user_id: int) -> bool:
    if not org_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM app_org_members WHERE org_id=%s AND user_id=%s AND status='active'",
        (int(org_id), int(user_id)),
    ).fetchone()
    return row is not None


def _can_access(conn, row: dict[str, Any], user_id: int) -> bool:
    if int(row.get("user_id") or 0) == int(user_id):
        return True
    return _org_member(conn, row.get("org_id"), user_id)


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("created_at", "updated_at"):
        out[key] = _iso(out.get(key))
    return out


def _snapshot_universe(conn, universe_id: int, user_id: int, version: int | None) -> dict[str, Any]:
    if version is None:
        row = conn.execute(
            "SELECT * FROM user_universe_versions WHERE universe_id=%s AND user_id=%s "
            "ORDER BY version_no DESC LIMIT 1",
            (universe_id, user_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM user_universe_versions WHERE universe_id=%s AND user_id=%s AND version_no=%s",
            (universe_id, user_id, version),
        ).fetchone()
    if not row:
        raise KeyError("版本不存在")
    symbols = list(row["symbols"] or [])
    return {
        "asset_id": str(universe_id),
        "version": f"v{row['version_no']}",
        "content_hash": row["content_hash"],
        "symbols": symbols,
        "constituent_count": len(symbols),
        "membership_mode": "static",
    }


def _snapshot_benchmark(conn, benchmark_id: int, user_id: int, version: int | None) -> dict[str, Any]:
    if version is None:
        row = conn.execute(
            "SELECT * FROM user_benchmark_versions WHERE benchmark_id=%s AND user_id=%s "
            "ORDER BY version_no DESC LIMIT 1",
            (benchmark_id, user_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM user_benchmark_versions WHERE benchmark_id=%s AND user_id=%s AND version_no=%s",
            (benchmark_id, user_id, version),
        ).fetchone()
    if not row:
        raise KeyError("版本不存在")
    weights = dict(row["weights"] or {})
    return {
        "asset_id": str(benchmark_id),
        "version": f"v{row['version_no']}",
        "content_hash": row["content_hash"],
        "weights": weights,
        "constituent_count": len(weights),
        "pricing": "close_to_close",
    }


def _insert_universe_version(conn, universe_id: int, user_id: int, version: int, symbols: list[str]) -> str:
    digest = _hash({"symbols": symbols})
    conn.execute(
        "INSERT INTO user_universe_versions (universe_id, user_id, version_no, symbols, content_hash) "
        "VALUES (%s,%s,%s,%s::jsonb,%s)",
        (universe_id, user_id, version, json.dumps(symbols, ensure_ascii=False), digest),
    )
    return digest


def _insert_benchmark_version(conn, benchmark_id: int, user_id: int, version: int, weights: dict[str, float]) -> str:
    digest = _hash({"weights": weights, "pricing": "close_to_close"})
    conn.execute(
        "INSERT INTO user_benchmark_versions (benchmark_id, user_id, version_no, weights, content_hash) "
        "VALUES (%s,%s,%s,%s::jsonb,%s)",
        (benchmark_id, user_id, version, json.dumps(weights, ensure_ascii=False), digest),
    )
    return digest


def create_universe(
    user_id: int,
    *,
    name: str,
    symbols: list[str],
    description: str = "",
    org_id: int | None = None,
) -> dict[str, Any]:
    ensure_asset_schema()
    title = (name or "").strip()
    if not (1 <= len(title) <= 60):
        raise ValueError("名称需 1–60 字")
    clean = _clean_symbols(symbols)
    with get_conn() as conn:
        if org_id and not _org_member(conn, org_id, user_id):
            raise PermissionError("不是该组织成员")
        exists = conn.execute(
            "SELECT 1 FROM user_universes WHERE user_id=%s AND name=%s AND org_id IS NOT DISTINCT FROM %s",
            (user_id, title, org_id)
        ).fetchone()
        if exists:
            raise ValueError("名称已存在")
        row = conn.execute(
            "INSERT INTO user_universes (user_id, name, description, org_id) "
            "VALUES (%s,%s,%s,%s) RETURNING *",
            (user_id, title, (description or "")[:200], org_id),
        ).fetchone()
        universe_id = int(row["id"])
        _insert_universe_version(conn, universe_id, user_id, 1, clean)
        snap = _snapshot_universe(conn, universe_id, user_id, None)
    return {**_row(dict(row)), "current_version": 1, "snapshot": snap}


def list_universes(user_id: int, *, org_id: int | None = None) -> list[dict[str, Any]]:
    ensure_asset_schema()
    with get_conn() as conn:
        if org_id:
            if not _org_member(conn, org_id, user_id):
                raise PermissionError("不是该组织成员")
            rows = conn.execute(
                "SELECT * FROM user_universes WHERE org_id=%s ORDER BY updated_at DESC", (org_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM user_universes WHERE user_id=%s AND org_id IS NULL "
                "ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        out = []
        for row in rows:
            item = _row(dict(row))
            item["snapshot"] = _snapshot_universe(conn, int(row["id"]), user_id, None)
            out.append(item)
    return out


def get_universe(user_id: int, universe_id: int, *, version: int | None = None) -> dict[str, Any]:
    ensure_asset_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_universes WHERE id=%s", (universe_id,)
        ).fetchone()
        if not row or not _can_access(conn, dict(row), user_id):
            raise KeyError(universe_id)
        snap = _snapshot_universe(conn, universe_id, int(row["user_id"]), version)
    return {**_row(dict(row)), "snapshot": snap}


def update_universe(
    user_id: int,
    universe_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    ensure_asset_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_universes WHERE id=%s", (universe_id,)
        ).fetchone()
        if not row or not _can_access(conn, dict(row), user_id):
            raise KeyError(universe_id)
        new_name = (name if name is not None else row["name"]).strip()
        if not (1 <= len(new_name) <= 60):
            raise ValueError("名称需 1–60 字")
        if new_name != row["name"]:
            clash = conn.execute(
                "SELECT 1 FROM user_universes WHERE user_id=%s AND name=%s AND id<>%s",
                (user_id, new_name, universe_id),
            ).fetchone()
            if clash:
                raise ValueError("名称已存在")
        new_desc = (description if description is not None else row["description"] or "")[:200]
        current = int(row["current_version"] or 1)
        digest = None
        if symbols is not None:
            clean = _clean_symbols(symbols)
            prev = _snapshot_universe(conn, universe_id, user_id, None)
            if clean != prev["symbols"]:
                current += 1
                digest = _insert_universe_version(conn, universe_id, user_id, current, clean)
        conn.execute(
            "UPDATE user_universes SET name=%s, description=%s, current_version=%s, updated_at=NOW() "
            "WHERE id=%s",
            (new_name, new_desc, current, universe_id),
        )
        snap = _snapshot_universe(conn, universe_id, user_id, None)
    return {
        **_row(dict(row)),
        "name": new_name,
        "description": new_desc,
        "current_version": current,
        "changed": digest is not None,
        "snapshot": snap,
    }


def delete_universe(user_id: int, universe_id: int) -> None:
    ensure_asset_schema()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_universes WHERE id=%s", (universe_id,)).fetchone()
        if not row or not _can_access(conn, dict(row), user_id):
            raise KeyError(universe_id)
        result = conn.execute("DELETE FROM user_universes WHERE id=%s", (universe_id,))
    if not getattr(result, "rowcount", 0):
        raise KeyError(universe_id)


def create_benchmark(
    user_id: int,
    *,
    name: str,
    weights: Any,
    description: str = "",
    org_id: int | None = None,
) -> dict[str, Any]:
    ensure_asset_schema()
    title = (name or "").strip()
    if not (1 <= len(title) <= 60):
        raise ValueError("名称需 1–60 字")
    clean = _clean_weights(weights)
    with get_conn() as conn:
        if org_id and not _org_member(conn, org_id, user_id):
            raise PermissionError("不是该组织成员")
        exists = conn.execute(
            "SELECT 1 FROM user_benchmarks WHERE user_id=%s AND name=%s AND org_id IS NOT DISTINCT FROM %s",
            (user_id, title, org_id)
        ).fetchone()
        if exists:
            raise ValueError("名称已存在")
        row = conn.execute(
            "INSERT INTO user_benchmarks (user_id, name, description, org_id) "
            "VALUES (%s,%s,%s,%s) RETURNING *",
            (user_id, title, (description or "")[:200], org_id),
        ).fetchone()
        benchmark_id = int(row["id"])
        _insert_benchmark_version(conn, benchmark_id, user_id, 1, clean)
        snap = _snapshot_benchmark(conn, benchmark_id, user_id, None)
    return {**_row(dict(row)), "current_version": 1, "snapshot": snap}


def list_benchmarks(user_id: int, *, org_id: int | None = None) -> list[dict[str, Any]]:
    ensure_asset_schema()
    with get_conn() as conn:
        if org_id:
            if not _org_member(conn, org_id, user_id):
                raise PermissionError("不是该组织成员")
            rows = conn.execute(
                "SELECT * FROM user_benchmarks WHERE org_id=%s ORDER BY updated_at DESC", (org_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM user_benchmarks WHERE user_id=%s AND org_id IS NULL "
                "ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        out = []
        for row in rows:
            item = _row(dict(row))
            item["snapshot"] = _snapshot_benchmark(conn, int(row["id"]), user_id, None)
            out.append(item)
    return out


def get_benchmark(user_id: int, benchmark_id: int, *, version: int | None = None) -> dict[str, Any]:
    ensure_asset_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_benchmarks WHERE id=%s", (benchmark_id,)
        ).fetchone()
        if not row or not _can_access(conn, dict(row), user_id):
            raise KeyError(benchmark_id)
        snap = _snapshot_benchmark(conn, benchmark_id, int(row["user_id"]), version)
    return {**_row(dict(row)), "snapshot": snap}


def update_benchmark(
    user_id: int,
    benchmark_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    weights: Any = None,
) -> dict[str, Any]:
    ensure_asset_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_benchmarks WHERE id=%s", (benchmark_id,)
        ).fetchone()
        if not row or not _can_access(conn, dict(row), user_id):
            raise KeyError(benchmark_id)
        new_name = (name if name is not None else row["name"]).strip()
        if not (1 <= len(new_name) <= 60):
            raise ValueError("名称需 1–60 字")
        if new_name != row["name"]:
            clash = conn.execute(
                "SELECT 1 FROM user_benchmarks WHERE user_id=%s AND name=%s AND id<>%s",
                (user_id, new_name, benchmark_id),
            ).fetchone()
            if clash:
                raise ValueError("名称已存在")
        new_desc = (description if description is not None else row["description"] or "")[:200]
        current = int(row["current_version"] or 1)
        digest = None
        if weights is not None:
            clean = _clean_weights(weights)
            prev = _snapshot_benchmark(conn, benchmark_id, user_id, None)
            if clean != prev["weights"]:
                current += 1
                digest = _insert_benchmark_version(conn, benchmark_id, user_id, current, clean)
        conn.execute(
            "UPDATE user_benchmarks SET name=%s, description=%s, current_version=%s, updated_at=NOW() "
            "WHERE id=%s",
            (new_name, new_desc, current, benchmark_id),
        )
        snap = _snapshot_benchmark(conn, benchmark_id, user_id, None)
    return {
        **_row(dict(row)),
        "name": new_name,
        "description": new_desc,
        "current_version": current,
        "changed": digest is not None,
        "snapshot": snap,
    }


def delete_benchmark(user_id: int, benchmark_id: int) -> None:
    ensure_asset_schema()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_benchmarks WHERE id=%s", (benchmark_id,)).fetchone()
        if not row or not _can_access(conn, dict(row), user_id):
            raise KeyError(benchmark_id)
        result = conn.execute("DELETE FROM user_benchmarks WHERE id=%s", (benchmark_id,))
    if not getattr(result, "rowcount", 0):
        raise KeyError(benchmark_id)


def resolve_universe_snapshot(user_id: int, asset_id: int, *, version: int | None = None) -> dict[str, Any]:
    ensure_asset_schema()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_universes WHERE id=%s", (asset_id,)).fetchone()
        if not row or not _can_access(conn, dict(row), user_id):
            raise KeyError(asset_id)
        return _snapshot_universe(conn, asset_id, int(row["user_id"]), version)


def resolve_benchmark_snapshot(user_id: int, asset_id: int, *, version: int | None = None) -> dict[str, Any]:
    ensure_asset_schema()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_benchmarks WHERE id=%s", (asset_id,)).fetchone()
        if not row or not _can_access(conn, dict(row), user_id):
            raise KeyError(asset_id)
        return _snapshot_benchmark(conn, asset_id, int(row["user_id"]), version)


def apply_asset_refs(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """把 universe_asset_id / benchmark_asset_id 解析成 RE 快照；与旧参数互斥。"""
    out = dict(payload or {})
    universe_id = out.pop("universe_asset_id", None)
    if universe_id is not None:
        version = out.pop("universe_version", None)
        out["universe_snapshot"] = resolve_universe_snapshot(
            user_id, int(universe_id), version=int(version) if version is not None else None
        )
        out.pop("universe", None)
    benchmark_id = out.pop("benchmark_asset_id", None)
    if benchmark_id is not None:
        version = out.pop("benchmark_version", None)
        out["benchmark_snapshot"] = resolve_benchmark_snapshot(
            user_id, int(benchmark_id), version=int(version) if version is not None else None
        )
        out.pop("benchmark", None)
    return out
