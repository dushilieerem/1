# -*- coding: utf-8 -*-
"""用户自选股组合（按 user_id 隔离）。标的主数据来自 YGQuant，此处只存关系。"""
from __future__ import annotations

import re
from typing import Any

from services.core.db import get_conn

NAME_RE = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff\- ]{0,63}$")
SYMBOL_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._\-]{0,31}$")


def ensure_watchlist_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_watchlists (
              id            BIGSERIAL PRIMARY KEY,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name          TEXT NOT NULL,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (user_id, name)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_watchlists_user "
            "ON user_watchlists (user_id, updated_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_watchlist_symbols (
              id              BIGSERIAL PRIMARY KEY,
              watchlist_id    BIGINT NOT NULL
                REFERENCES user_watchlists(id) ON DELETE CASCADE,
              user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              symbol          TEXT NOT NULL,
              name            TEXT NOT NULL DEFAULT '',
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (watchlist_id, symbol)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_watchlist_symbols_wl "
            "ON user_watchlist_symbols (watchlist_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_watchlist_symbols_user "
            "ON user_watchlist_symbols (user_id, created_at DESC)"
        )


def _iso(val: Any) -> Any:
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def _wl_row(r: dict[str, Any], symbol_count: int = 0) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "name": r["name"],
        "createdAt": _iso(r.get("created_at")),
        "updatedAt": _iso(r.get("updated_at")),
        "symbolCount": int(symbol_count),
    }


def _sym_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "watchlistId": int(r["watchlist_id"]),
        "symbol": r["symbol"],
        "name": r.get("name") or "",
        "createdAt": _iso(r.get("created_at")),
    }


def _require_watchlist(conn: Any, user_id: int, watchlist_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, name, created_at, updated_at FROM user_watchlists "
        "WHERE id = %s AND user_id = %s",
        (int(watchlist_id), int(user_id)),
    ).fetchone()
    if not row:
        raise KeyError("watchlist not found")
    return dict(row)


def list_watchlists(user_id: int) -> list[dict[str, Any]]:
    ensure_watchlist_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT w.id, w.name, w.created_at, w.updated_at,
                   COALESCE(c.cnt, 0) AS symbol_count
            FROM user_watchlists w
            LEFT JOIN (
              SELECT watchlist_id, COUNT(*) AS cnt
              FROM user_watchlist_symbols
              GROUP BY watchlist_id
            ) c ON c.watchlist_id = w.id
            WHERE w.user_id = %s
            ORDER BY w.updated_at DESC, w.id DESC
            """,
            (int(user_id),),
        ).fetchall()
    return [_wl_row(dict(r), int(dict(r).get("symbol_count") or 0)) for r in rows]


def create_watchlist(user_id: int, name: str) -> dict[str, Any]:
    ensure_watchlist_schema()
    title = (name or "").strip()
    if not title:
        raise ValueError("请填写自选组合名称")
    if title in ("浏览选股", "全部"):
        raise ValueError(f"不能使用保留名：{title}")
    if not NAME_RE.match(title):
        raise ValueError("名称仅支持中英文、数字、下划线、短横线，最长 64")
    with get_conn() as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO user_watchlists (user_id, name)
                VALUES (%s, %s)
                RETURNING id, name, created_at, updated_at
                """,
                (int(user_id), title),
            ).fetchone()
        except Exception as exc:
            msg = str(exc).lower()
            if "unique" in msg or "duplicate" in msg:
                raise ValueError("同名自选组合已存在") from exc
            raise
    return _wl_row(dict(row), 0)


def rename_watchlist(user_id: int, watchlist_id: int, name: str) -> dict[str, Any]:
    ensure_watchlist_schema()
    title = (name or "").strip()
    if not title:
        raise ValueError("请填写自选组合名称")
    if title in ("浏览选股", "全部"):
        raise ValueError(f"不能使用保留名：{title}")
    if not NAME_RE.match(title):
        raise ValueError("名称仅支持中英文、数字、下划线、短横线，最长 64")
    with get_conn() as conn:
        _require_watchlist(conn, user_id, watchlist_id)
        try:
            row = conn.execute(
                """
                UPDATE user_watchlists
                SET name = %s, updated_at = NOW()
                WHERE id = %s AND user_id = %s
                RETURNING id, name, created_at, updated_at
                """,
                (title, int(watchlist_id), int(user_id)),
            ).fetchone()
        except Exception as exc:
            msg = str(exc).lower()
            if "unique" in msg or "duplicate" in msg:
                raise ValueError("同名自选组合已存在") from exc
            raise
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM user_watchlist_symbols "
            "WHERE watchlist_id = %s AND user_id = %s",
            (int(watchlist_id), int(user_id)),
        ).fetchone()
    return _wl_row(dict(row), int(dict(cnt).get("c") or 0))


def delete_watchlist(user_id: int, watchlist_id: int) -> dict[str, Any]:
    ensure_watchlist_schema()
    with get_conn() as conn:
        _require_watchlist(conn, user_id, watchlist_id)
        conn.execute(
            "DELETE FROM user_watchlists WHERE id = %s AND user_id = %s",
            (int(watchlist_id), int(user_id)),
        )
    return {"ok": True}


def list_watchlist_symbols(user_id: int, watchlist_id: int) -> list[dict[str, Any]]:
    ensure_watchlist_schema()
    with get_conn() as conn:
        _require_watchlist(conn, user_id, watchlist_id)
        rows = conn.execute(
            """
            SELECT id, watchlist_id, symbol, name, created_at
            FROM user_watchlist_symbols
            WHERE watchlist_id = %s AND user_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (int(watchlist_id), int(user_id)),
        ).fetchall()
    return [_sym_row(dict(r)) for r in rows]


def _normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s or not SYMBOL_RE.match(s):
        raise ValueError("无效股票代码")
    return s


def add_watchlist_symbol(
    user_id: int,
    watchlist_id: int,
    symbol: str,
    name: str = "",
) -> dict[str, Any]:
    ensure_watchlist_schema()
    code = _normalize_symbol(symbol)
    label = (name or "").strip()
    with get_conn() as conn:
        _require_watchlist(conn, user_id, watchlist_id)
        existing = conn.execute(
            "SELECT id, watchlist_id, symbol, name, created_at "
            "FROM user_watchlist_symbols "
            "WHERE watchlist_id = %s AND symbol = %s",
            (int(watchlist_id), code),
        ).fetchone()
        if existing:
            if label and not (dict(existing).get("name") or "").strip():
                conn.execute(
                    "UPDATE user_watchlist_symbols SET name = %s WHERE id = %s",
                    (label, int(dict(existing)["id"])),
                )
                row = conn.execute(
                    "SELECT id, watchlist_id, symbol, name, created_at "
                    "FROM user_watchlist_symbols WHERE id = %s",
                    (int(dict(existing)["id"]),),
                ).fetchone()
                return _sym_row(dict(row))
            return _sym_row(dict(existing))
        row = conn.execute(
            """
            INSERT INTO user_watchlist_symbols (watchlist_id, user_id, symbol, name)
            VALUES (%s, %s, %s, %s)
            RETURNING id, watchlist_id, symbol, name, created_at
            """,
            (int(watchlist_id), int(user_id), code, label),
        ).fetchone()
        conn.execute(
            "UPDATE user_watchlists SET updated_at = NOW() "
            "WHERE id = %s AND user_id = %s",
            (int(watchlist_id), int(user_id)),
        )
    return _sym_row(dict(row))


def add_watchlist_symbols_batch(
    user_id: int,
    watchlist_id: int,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    ensure_watchlist_schema()
    if not items:
        raise ValueError("请选择至少一只股票")
    # ownership check once
    with get_conn() as conn:
        _require_watchlist(conn, user_id, watchlist_id)

    added = 0
    skipped = 0
    out: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        try:
            code = _normalize_symbol(str(raw.get("symbol") or ""))
        except ValueError:
            skipped += 1
            continue
        with get_conn() as conn:
            existed = conn.execute(
                "SELECT 1 FROM user_watchlist_symbols "
                "WHERE watchlist_id = %s AND symbol = %s",
                (int(watchlist_id), code),
            ).fetchone()
        row = add_watchlist_symbol(
            user_id,
            watchlist_id,
            code,
            str(raw.get("name") or ""),
        )
        out.append(row)
        if existed:
            skipped += 1
        else:
            added += 1
    return {"ok": True, "added": added, "skipped": skipped, "symbols": out}


def delete_watchlist_symbol(
    user_id: int, watchlist_id: int, symbol: str
) -> dict[str, Any]:
    ensure_watchlist_schema()
    code = _normalize_symbol(symbol)
    with get_conn() as conn:
        _require_watchlist(conn, user_id, watchlist_id)
        existed = conn.execute(
            "SELECT id FROM user_watchlist_symbols "
            "WHERE watchlist_id = %s AND user_id = %s AND symbol = %s",
            (int(watchlist_id), int(user_id), code),
        ).fetchone()
        if not existed:
            raise KeyError("symbol not found")
        conn.execute(
            "DELETE FROM user_watchlist_symbols WHERE id = %s",
            (int(dict(existed)["id"]),),
        )
        conn.execute(
            "UPDATE user_watchlists SET updated_at = NOW() "
            "WHERE id = %s AND user_id = %s",
            (int(watchlist_id), int(user_id)),
        )
    return {"ok": True}
