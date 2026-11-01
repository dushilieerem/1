# -*- coding: utf-8 -*-
"""用户自建策略库（文件夹）。与「内置策略库」同级；库内策略后续入库。"""
from __future__ import annotations

import json
import re
from typing import Any

from services.core.db import get_conn

NAME_RE = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff\-]{0,63}$")
MAX_LIBRARY_NAME_LEN = 64


def ensure_user_strategy_libraries_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_strategy_libraries (
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
            "CREATE INDEX IF NOT EXISTS idx_user_strategy_libraries_user "
            "ON user_strategy_libraries (user_id, updated_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_library_strategies (
              id              BIGSERIAL PRIMARY KEY,
              library_id      BIGINT NOT NULL
                REFERENCES user_strategy_libraries(id) ON DELETE CASCADE,
              user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name            TEXT NOT NULL,
              code_id         TEXT NOT NULL DEFAULT '',
              body            TEXT NOT NULL DEFAULT '',
              description     TEXT NOT NULL DEFAULT '',
              category_label  TEXT NOT NULL DEFAULT '其他',
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (library_id, name)
            )
            """
        )
        # 策略名唯一性收敛到库内：不同策略库允许同名策略。
        # 历史版本建过全用户范围的 UNIQUE (user_id, name)，对已存在的表移除。
        conn.execute(
            "ALTER TABLE user_library_strategies "
            "DROP CONSTRAINT IF EXISTS user_library_strategies_user_id_name_key"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_library_strategy_versions (
              id BIGSERIAL PRIMARY KEY,
              library_strategy_id BIGINT NOT NULL
                REFERENCES user_library_strategies(id) ON DELETE CASCADE,
              user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              version_no INTEGER NOT NULL,
              name TEXT NOT NULL,
              code_id TEXT NOT NULL DEFAULT '',
              body TEXT NOT NULL DEFAULT '',
              description TEXT NOT NULL DEFAULT '',
              category_label TEXT NOT NULL DEFAULT '其他',
              source_run_id TEXT NOT NULL DEFAULT '',
              archive_request JSONB,
              archive_result JSONB,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (library_strategy_id, version_no)
            )
            """
        )
        # 入库快照：与研究侧 run 脱钩，不可变
        for stmt in (
            "ALTER TABLE user_library_strategies "
            "ADD COLUMN IF NOT EXISTS source_run_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE user_library_strategies "
            "ADD COLUMN IF NOT EXISTS archive_request JSONB",
            "ALTER TABLE user_library_strategies "
            "ADD COLUMN IF NOT EXISTS archive_result JSONB",
            "ALTER TABLE user_library_strategies "
            "ADD COLUMN IF NOT EXISTS archive_elapsed_sec DOUBLE PRECISION",
            "ALTER TABLE user_library_strategies "
            "ADD COLUMN IF NOT EXISTS archive_finished_at TIMESTAMPTZ",
            # 新建默认待检测；回测成功后写入 detected_at
            "ALTER TABLE user_library_strategies "
            "ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ",
        ):
            conn.execute(stmt)
        # 旧入库快照视为已检测
        conn.execute(
            """
            UPDATE user_library_strategies
            SET detected_at = COALESCE(archive_finished_at, created_at, NOW())
            WHERE detected_at IS NULL AND archive_result IS NOT NULL
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_library_strategies_lib "
            "ON user_library_strategies (library_id, updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_library_strategies_user "
            "ON user_library_strategies (user_id, updated_at DESC)"
        )


def _iso(val: Any) -> Any:
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def _as_json(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return None
    return None


def _lib_row(r: dict[str, Any], strategy_count: int = 0) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "name": r["name"],
        "createdAt": _iso(r.get("created_at")),
        "updatedAt": _iso(r.get("updated_at")),
        "strategyCount": int(strategy_count),
    }


def _strategy_row(
    r: dict[str, Any], library_name: str | None = None
) -> dict[str, Any]:
    has_archive = _as_json(r.get("archive_result")) is not None
    detected_at = _iso(r.get("detected_at"))
    pending_detect = detected_at is None and not has_archive
    return {
        "id": int(r["id"]),
        "libraryId": int(r["library_id"]),
        "libraryName": library_name or "",
        "name": r["name"],
        "codeId": r.get("code_id") or "",
        "body": r.get("body") or "",
        "description": r.get("description") or "",
        "categoryLabel": r.get("category_label") or "其他",
        "sourceRunId": r.get("source_run_id") or "",
        "hasArchiveReport": has_archive,
        "archiveFinishedAt": _iso(r.get("archive_finished_at")),
        "detectedAt": detected_at,
        "pendingDetect": pending_detect,
        "createdAt": _iso(r.get("created_at")),
        "updatedAt": _iso(r.get("updated_at")),
    }


def list_user_strategy_libraries(user_id: int) -> list[dict[str, Any]]:
    ensure_user_strategy_libraries_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT l.id, l.name, l.created_at, l.updated_at,
                   COALESCE(c.cnt, 0) AS strategy_count
            FROM user_strategy_libraries l
            LEFT JOIN (
              SELECT library_id, COUNT(*)::int AS cnt
              FROM user_library_strategies
              GROUP BY library_id
            ) c ON c.library_id = l.id
            WHERE l.user_id = %s
            ORDER BY l.updated_at DESC, l.id DESC
            """,
            (int(user_id),),
        ).fetchall()
    return [_lib_row(dict(r), int(dict(r).get("strategy_count") or 0)) for r in rows]


def create_user_strategy_library(user_id: int, name: str) -> dict[str, Any]:
    ensure_user_strategy_libraries_schema()
    title = (name or "").strip()
    if not title:
        raise ValueError("请填写策略库名称")
    if len(title) > MAX_LIBRARY_NAME_LEN:
        raise ValueError(
            f"策略库名称最长 {MAX_LIBRARY_NAME_LEN} 个字符，当前 {len(title)} 个"
        )
    if not NAME_RE.match(title):
        raise ValueError("名称仅支持中英文、数字、下划线与短横线")
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT id FROM user_strategy_libraries WHERE user_id = %s AND name = %s",
            (int(user_id), title),
        ).fetchone()
        if exists:
            raise ValueError(f"已存在同名策略库：{title}")
        row = conn.execute(
            """
            INSERT INTO user_strategy_libraries (user_id, name)
            VALUES (%s, %s)
            RETURNING *
            """,
            (int(user_id), title),
        ).fetchone()
    return _lib_row(dict(row), 0)


def delete_user_strategy_library(user_id: int, library_id: int) -> dict[str, Any]:
    ensure_user_strategy_libraries_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            DELETE FROM user_strategy_libraries
            WHERE user_id = %s AND id = %s
            RETURNING id, name
            """,
            (int(user_id), int(library_id)),
        ).fetchone()
        if not row:
            raise KeyError(library_id)
    return {"ok": True, "id": int(row["id"]), "name": row["name"]}


def list_library_strategies(user_id: int, library_id: int) -> list[dict[str, Any]]:
    ensure_user_strategy_libraries_schema()
    with get_conn() as conn:
        lib = conn.execute(
            "SELECT id, name FROM user_strategy_libraries WHERE user_id = %s AND id = %s",
            (int(user_id), int(library_id)),
        ).fetchone()
        if not lib:
            raise KeyError(library_id)
        rows = conn.execute(
            """
            SELECT id, library_id, user_id, name, code_id, body, description,
                   category_label, source_run_id, archive_finished_at,
                   detected_at, created_at, updated_at,
                   (archive_result IS NOT NULL) AS has_archive
            FROM user_library_strategies
            WHERE user_id = %s AND library_id = %s
            ORDER BY updated_at DESC, id DESC
            """,
            (int(user_id), int(library_id)),
        ).fetchall()
    lib_name = dict(lib)["name"]
    out = []
    for r in rows:
        d = dict(r)
        if d.get("has_archive"):
            d["archive_result"] = {"_present": True}
        else:
            d["archive_result"] = None
        out.append(_strategy_row(d, lib_name))
    return out


def add_library_strategy(
    user_id: int,
    library_id: int,
    *,
    name: str,
    body: str,
    description: str = "",
    category_label: str = "其他",
    code_id: str = "",
    source_run_id: str = "",
    archive_request: Any = None,
    archive_result: Any = None,
    archive_elapsed_sec: float | None = None,
    archive_finished_at: str | None = None,
) -> dict[str, Any]:
    """将某次回测的代码/参数入库；可附带不可变回测快照。"""
    ensure_user_strategy_libraries_schema()
    title = (name or "").strip()
    if not title:
        raise ValueError("请填写策略名称")
    if len(title) > 80:
        raise ValueError("策略名称过长（最多 80 字）")
    code = (body or "").strip()
    if not code:
        raise ValueError("策略代码不能为空")
    desc = (description or "").strip() or title
    if len(desc) > 40:
        raise ValueError("策略说明过长（最多 40 字）")
    cat = (category_label or "其他").strip() or "其他"
    cid = (code_id or "").strip() or title
    run_id = (source_run_id or "").strip()
    req_obj = archive_request if isinstance(archive_request, dict) else None
    res_obj = archive_result if isinstance(archive_result, dict) else None
    if res_obj is not None and not req_obj:
        res_obj = None
    elapsed = archive_elapsed_sec
    if elapsed is not None:
        try:
            elapsed = float(elapsed)
        except (TypeError, ValueError):
            elapsed = None

    req_json = json.dumps(req_obj, ensure_ascii=False) if req_obj is not None else None
    res_json = json.dumps(res_obj, ensure_ascii=False) if res_obj is not None else None

    with get_conn() as conn:
        lib = conn.execute(
            "SELECT id, name FROM user_strategy_libraries WHERE user_id = %s AND id = %s",
            (int(user_id), int(library_id)),
        ).fetchone()
        if not lib:
            raise KeyError(library_id)
        clash = conn.execute(
            "SELECT id, library_id FROM user_library_strategies "
            "WHERE library_id = %s AND name = %s",
            (int(library_id), title),
        ).fetchone()
        if clash:
            raise ValueError(f"该策略库中已有同名策略「{title}」，请换一个名字")
        row = conn.execute(
            """
            INSERT INTO user_library_strategies
              (library_id, user_id, name, code_id, body, description, category_label,
               source_run_id, archive_request, archive_result,
               archive_elapsed_sec, archive_finished_at, detected_at)
            VALUES (
              %s, %s, %s, %s, %s, %s, %s,
              %s, %s::jsonb, %s::jsonb,
              %s,
              COALESCE(%s::timestamptz, CASE WHEN %s::jsonb IS NOT NULL THEN NOW() ELSE NULL END),
              CASE WHEN %s::jsonb IS NOT NULL THEN NOW() ELSE NULL END
            )
            RETURNING *
            """,
            (
                int(library_id),
                int(user_id),
                title,
                cid,
                code,
                desc,
                cat,
                run_id,
                req_json,
                res_json,
                elapsed,
                archive_finished_at,
                res_json,
                res_json,
            ),
        ).fetchone()
        conn.execute(
            "UPDATE user_strategy_libraries SET updated_at = NOW() WHERE id = %s",
            (int(library_id),),
        )
    _insert_strategy_version(int(row["id"]), int(user_id), 1, dict(row))
    return _strategy_row(dict(row), dict(lib)["name"])


def _insert_strategy_version(strategy_id: int, user_id: int, version_no: int, row: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO user_library_strategy_versions
              (library_strategy_id, user_id, version_no, name, code_id, body, description,
               category_label, source_run_id, archive_request, archive_result)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
            ON CONFLICT (library_strategy_id, version_no) DO NOTHING
            """,
            (
                strategy_id, user_id, version_no, row.get("name") or "", row.get("code_id") or "",
                row.get("body") or "", row.get("description") or "", row.get("category_label") or "其他",
                row.get("source_run_id") or "",
                json.dumps(row.get("archive_request"), ensure_ascii=False) if row.get("archive_request") is not None else None,
                json.dumps(row.get("archive_result"), ensure_ascii=False) if row.get("archive_result") is not None else None,
            ),
        )


def update_library_strategy(
    user_id: int,
    strategy_id: int,
    *,
    name: str | None = None,
    body: str | None = None,
    description: str | None = None,
    category_label: str | None = None,
) -> dict[str, Any]:
    """更新库内策略并保留版本快照（P1-S03）。"""
    ensure_user_strategy_libraries_schema()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT s.*, l.name AS library_name FROM user_library_strategies s "
            "JOIN user_strategy_libraries l ON l.id=s.library_id "
            "WHERE s.id=%s AND s.user_id=%s",
            (int(strategy_id), int(user_id)),
        ).fetchone()
        if not row:
            raise KeyError(strategy_id)
        cur = dict(row)
        new_name = (name if name is not None else cur["name"] or "").strip()
        if not new_name:
            raise ValueError("请填写策略名称")
        if len(new_name) > 80:
            raise ValueError("策略名称过长（最多 80 字）")
        if new_name != cur["name"]:
            clash = conn.execute(
                "SELECT 1 FROM user_library_strategies WHERE library_id=%s AND name=%s AND id<>%s",
                (cur["library_id"], new_name, strategy_id),
            ).fetchone()
            if clash:
                raise ValueError("该策略库中已有同名策略")
        new_body = (body if body is not None else cur["body"] or "").strip()
        if not new_body:
            raise ValueError("策略代码不能为空")
        new_desc = (description if description is not None else cur["description"] or "").strip() or new_name
        if len(new_desc) > 40:
            raise ValueError("策略说明过长（最多 40 字）")
        new_cat = (category_label if category_label is not None else cur["category_label"] or "其他").strip() or "其他"
        updated = conn.execute(
            """
            UPDATE user_library_strategies
               SET name=%s, body=%s, description=%s, category_label=%s, updated_at=NOW()
             WHERE id=%s AND user_id=%s RETURNING *
            """,
            (new_name, new_body, new_desc, new_cat, strategy_id, user_id),
        ).fetchone()
        version = conn.execute(
            "SELECT COALESCE(MAX(version_no),0)+1 AS n FROM user_library_strategy_versions WHERE library_strategy_id=%s",
            (strategy_id,),
        ).fetchone()["n"]
    _insert_strategy_version(int(strategy_id), int(user_id), int(version), dict(updated))
    return _strategy_row(dict(updated), cur["library_name"])


def list_library_strategy_versions(
    user_id: int, strategy_id: int, *, limit: int = 50
) -> list[dict[str, Any]]:
    """策略版本历史（FEAT-017）：只返回元数据，不返回代码正文。"""
    ensure_user_strategy_libraries_schema()
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM user_library_strategies WHERE id=%s AND user_id=%s",
            (int(strategy_id), int(user_id)),
        ).fetchone()
        if not exists:
            raise KeyError(strategy_id)
        rows = conn.execute(
            """
            SELECT id, version_no, name, description, category_label, source_run_id,
                   created_at, length(body) AS body_chars
              FROM user_library_strategy_versions
             WHERE library_strategy_id=%s AND user_id=%s
             ORDER BY version_no DESC
             LIMIT %s
            """,
            (int(strategy_id), int(user_id), max(1, min(int(limit), 200))),
        ).fetchall()
    return [_iso_row(dict(r)) for r in rows]


def get_library_strategy_version(
    user_id: int, strategy_id: int, version_no: int
) -> dict[str, Any]:
    """读取指定版本的完整快照（含代码正文）。"""
    ensure_user_strategy_libraries_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT version_no, name, code_id, body, description, category_label,
                   source_run_id, created_at
              FROM user_library_strategy_versions
             WHERE library_strategy_id=%s AND user_id=%s AND version_no=%s
            """,
            (int(strategy_id), int(user_id), int(version_no)),
        ).fetchone()
    if not row:
        raise KeyError(version_no)
    return _iso_row(dict(row))


def _iso_row(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("created_at", "updated_at"):
        row[key] = _iso(row.get(key))
    return row


def get_library_strategy_archive(user_id: int, strategy_id: int) -> dict[str, Any]:
    """返回入库时冻结的回测报告（只读）。"""
    ensure_user_strategy_libraries_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT s.*, l.name AS library_name
            FROM user_library_strategies s
            JOIN user_strategy_libraries l ON l.id = s.library_id
            WHERE s.user_id = %s AND s.id = %s
            """,
            (int(user_id), int(strategy_id)),
        ).fetchone()
    if not row:
        raise KeyError(strategy_id)
    d = dict(row)
    req = _as_json(d.get("archive_request")) or {}
    res = _as_json(d.get("archive_result"))
    if res is None:
        raise ValueError("该策略没有入库回测快照（旧数据仅保存了代码）")
    return {
        "ok": True,
        "run": {
            "id": f"libarch:{int(d['id'])}",
            "projectId": "",
            "name": d.get("name") or "",
            "description": d.get("description") or d.get("name") or "",
            "request": req if isinstance(req, dict) else {},
            "result": res if isinstance(res, dict) else {},
            "finishedAt": _iso(d.get("archive_finished_at"))
            or _iso(d.get("created_at")),
            "elapsedSec": float(d.get("archive_elapsed_sec") or 0),
            "immutable": True,
            "sourceRunId": d.get("source_run_id") or "",
            "libraryId": int(d["library_id"]),
            "libraryStrategyId": int(d["id"]),
            "libraryName": d.get("library_name") or "",
        },
    }


def mark_library_strategy_detected(
    user_id: int, strategy_id: int
) -> dict[str, Any]:
    """首次回测成功后去掉「待检测」。"""
    ensure_user_strategy_libraries_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE user_library_strategies
            SET detected_at = COALESCE(detected_at, NOW()),
                updated_at = NOW()
            WHERE user_id = %s AND id = %s
            RETURNING *
            """,
            (int(user_id), int(strategy_id)),
        ).fetchone()
        if not row:
            raise KeyError(strategy_id)
        lib = conn.execute(
            "SELECT name FROM user_strategy_libraries WHERE id = %s",
            (int(dict(row)["library_id"]),),
        ).fetchone()
        conn.execute(
            "UPDATE user_strategy_libraries SET updated_at = NOW() WHERE id = %s",
            (int(dict(row)["library_id"]),),
        )
    return _strategy_row(dict(row), dict(lib)["name"] if lib else "")


def delete_library_strategy(
    user_id: int, library_id: int, strategy_id: int
) -> dict[str, Any]:
    ensure_user_strategy_libraries_schema()
    with get_conn() as conn:
        lib = conn.execute(
            "SELECT id, name FROM user_strategy_libraries WHERE user_id = %s AND id = %s",
            (int(user_id), int(library_id)),
        ).fetchone()
        if not lib:
            raise KeyError(library_id)
        row = conn.execute(
            """
            DELETE FROM user_library_strategies
            WHERE user_id = %s AND library_id = %s AND id = %s
            RETURNING id, name
            """,
            (int(user_id), int(library_id), int(strategy_id)),
        ).fetchone()
        if not row:
            raise KeyError(strategy_id)
        conn.execute(
            "UPDATE user_strategy_libraries SET updated_at = NOW() WHERE id = %s",
            (int(library_id),),
        )
    return {
        "ok": True,
        "id": int(row["id"]),
        "name": row["name"],
        "libraryId": int(library_id),
    }
