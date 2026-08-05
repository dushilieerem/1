# -*- coding: utf-8 -*-
"""用户自建因子库（文件夹）+ 库内因子。与「内置因子库」同级。"""
from __future__ import annotations

import re
from typing import Any

from services.db import get_conn

NAME_RE = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff\-]{0,63}$")
FACTOR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ensure_user_libraries_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_factor_libraries (
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
            "CREATE INDEX IF NOT EXISTS idx_user_factor_libraries_user "
            "ON user_factor_libraries (user_id, updated_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_library_factors (
              id              BIGSERIAL PRIMARY KEY,
              library_id      BIGINT NOT NULL
                REFERENCES user_factor_libraries(id) ON DELETE CASCADE,
              user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name            TEXT NOT NULL,
              method_name     TEXT NOT NULL,
              body            TEXT NOT NULL,
              description     TEXT NOT NULL DEFAULT '',
              category_label  TEXT NOT NULL DEFAULT '其他',
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (library_id, name),
              UNIQUE (user_id, name)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_library_factors_lib "
            "ON user_library_factors (library_id, updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_library_factors_user "
            "ON user_library_factors (user_id, updated_at DESC)"
        )


def _iso(val: Any) -> Any:
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def _lib_row(r: dict[str, Any], factor_count: int = 0) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "name": r["name"],
        "createdAt": _iso(r.get("created_at")),
        "updatedAt": _iso(r.get("updated_at")),
        "factorCount": int(factor_count),
    }


def _factor_row(r: dict[str, Any], library_name: str | None = None) -> dict[str, Any]:
    lib_id = int(r["library_id"])
    return {
        "id": int(r["id"]),
        "libraryId": lib_id,
        "libraryName": library_name or "",
        "name": r["name"],
        "methodName": r.get("method_name") or r["name"],
        "body": r.get("body") or "",
        "description": r.get("description") or "",
        "categoryLabel": r.get("category_label") or "其他",
        "createdAt": _iso(r.get("created_at")),
        "updatedAt": _iso(r.get("updated_at")),
    }


def list_user_libraries(user_id: int) -> list[dict[str, Any]]:
    ensure_user_libraries_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT l.id, l.name, l.created_at, l.updated_at,
                   COALESCE(c.cnt, 0) AS factor_count
            FROM user_factor_libraries l
            LEFT JOIN (
              SELECT library_id, COUNT(*) AS cnt
              FROM user_library_factors
              GROUP BY library_id
            ) c ON c.library_id = l.id
            WHERE l.user_id = %s
            ORDER BY l.updated_at DESC, l.id DESC
            """,
            (int(user_id),),
        ).fetchall()
    return [_lib_row(dict(r), int(dict(r).get("factor_count") or 0)) for r in rows]


def create_user_library(user_id: int, name: str) -> dict[str, Any]:
    ensure_user_libraries_schema()
    title = (name or "").strip()
    if not title:
        raise ValueError("请填写因子库名称")
    if title in ("内置因子库", "全部", "其他"):
        raise ValueError(f"不能使用保留名：{title}")
    if not NAME_RE.match(title):
        raise ValueError("名称仅支持中英文、数字、下划线与短横线，最长 64")
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id FROM user_factor_libraries WHERE user_id = %s AND name = %s",
            (int(user_id), title),
        ).fetchone()
        if exists:
            raise ValueError(f"已存在同名因子库：{title}")
        row = conn.execute(
            """
            INSERT INTO user_factor_libraries (user_id, name)
            VALUES (%s, %s)
            RETURNING id, name, created_at, updated_at
            """,
            (int(user_id), title),
        ).fetchone()
    return _lib_row(dict(row), 0)


def delete_user_library(user_id: int, library_id: int) -> dict[str, Any]:
    ensure_user_libraries_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            DELETE FROM user_factor_libraries
            WHERE user_id = %s AND id = %s
            RETURNING id, name
            """,
            (int(user_id), int(library_id)),
        ).fetchone()
    if not row:
        raise KeyError(library_id)
    return {"ok": True, "id": int(row["id"]), "name": row["name"]}


def _extract_def_name(body: str) -> str | None:
    m = re.search(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", body or "", flags=re.M)
    return m.group(1) if m else None


def _normalize_body(body: str, name: str, description: str = "") -> str:
    e = (body or "").strip()
    if not e:
        raise ValueError("因子代码不能为空")
    doc = (description or name).replace("\\", "\\\\").replace('"""', "'''")
    if not e.lstrip().startswith("def "):
        if "return" not in e:
            e = f"return {e}"
        e = f'def {name}(self):\n    """{doc}"""\n    ' + e.replace("\n", "\n    ")
        return e
    def_name = _extract_def_name(e)
    if not def_name:
        raise ValueError("请写完整函数，例如 def my_factor(self): ...")
    if def_name != name:
        raise ValueError(f"因子代码名「{name}」须与函数名「{def_name}」一致")
    return e


def list_library_factors(user_id: int, library_id: int) -> list[dict[str, Any]]:
    ensure_user_libraries_schema()
    with get_conn() as conn:
        lib = conn.execute(
            "SELECT id, name FROM user_factor_libraries WHERE user_id = %s AND id = %s",
            (int(user_id), int(library_id)),
        ).fetchone()
        if not lib:
            raise KeyError(library_id)
        rows = conn.execute(
            """
            SELECT *
            FROM user_library_factors
            WHERE user_id = %s AND library_id = %s
            ORDER BY updated_at DESC, id DESC
            """,
            (int(user_id), int(library_id)),
        ).fetchall()
    lib_name = dict(lib)["name"]
    return [_factor_row(dict(r), lib_name) for r in rows]


def list_all_user_library_factors(user_id: int) -> list[dict[str, Any]]:
    ensure_user_libraries_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT f.*, l.name AS library_name
            FROM user_library_factors f
            JOIN user_factor_libraries l ON l.id = f.library_id
            WHERE f.user_id = %s
            ORDER BY f.updated_at DESC, f.id DESC
            """,
            (int(user_id),),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        out.append(_factor_row(d, d.get("library_name") or ""))
    return out


def add_library_factor(
    user_id: int,
    library_id: int,
    *,
    name: str,
    body: str,
    description: str = "",
    category_label: str = "其他",
) -> dict[str, Any]:
    ensure_user_libraries_schema()
    code = (name or "").strip()
    if not code:
        raise ValueError("请填写因子代码名")
    if not FACTOR_NAME_RE.match(code):
        raise ValueError("因子代码名仅支持字母开头的标识符（字母/数字/下划线）")
    desc = (description or "").strip() or code
    cat = (category_label or "其他").strip() or "其他"
    normalized = _normalize_body(body, code, desc)

    with get_conn() as conn:
        lib = conn.execute(
            "SELECT id, name FROM user_factor_libraries WHERE user_id = %s AND id = %s",
            (int(user_id), int(library_id)),
        ).fetchone()
        if not lib:
            raise KeyError(library_id)
        clash = conn.execute(
            "SELECT id, library_id FROM user_library_factors WHERE user_id = %s AND name = %s",
            (int(user_id), code),
        ).fetchone()
        if clash:
            raise ValueError(f"你已有同名因子「{code}」，请换一个代码名")
        row = conn.execute(
            """
            INSERT INTO user_library_factors
              (library_id, user_id, name, method_name, body, description, category_label)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                int(library_id),
                int(user_id),
                code,
                code,
                normalized,
                desc,
                cat,
            ),
        ).fetchone()
        conn.execute(
            "UPDATE user_factor_libraries SET updated_at = NOW() WHERE id = %s",
            (int(library_id),),
        )
    return _factor_row(dict(row), dict(lib)["name"])


def delete_library_factor(
    user_id: int, library_id: int, factor_id: int
) -> dict[str, Any]:
    ensure_user_libraries_schema()
    with get_conn() as conn:
        lib = conn.execute(
            "SELECT id, name FROM user_factor_libraries WHERE user_id = %s AND id = %s",
            (int(user_id), int(library_id)),
        ).fetchone()
        if not lib:
            raise KeyError(library_id)
        row = conn.execute(
            """
            DELETE FROM user_library_factors
            WHERE user_id = %s AND library_id = %s AND id = %s
            RETURNING id, name
            """,
            (int(user_id), int(library_id), int(factor_id)),
        ).fetchone()
        if not row:
            raise KeyError(factor_id)
        conn.execute(
            "UPDATE user_factor_libraries SET updated_at = NOW() WHERE id = %s",
            (int(library_id),),
        )
    return {
        "ok": True,
        "id": int(row["id"]),
        "name": row["name"],
        "libraryId": int(library_id),
    }
