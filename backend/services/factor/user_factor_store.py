# -*- coding: utf-8 -*-
"""按用户隔离的自定义因子：Postgres 权威 + 同步 custom_lib.py / index.yaml。"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from services.core.db import get_conn

FACTOR_DIR = Path(__file__).resolve().parents[2] / "factor"
INDEX_PATH = FACTOR_DIR / "index.yaml"
CUSTOM_FILE = "custom_lib.py"
CUSTOM_CLASS = "CustomLib"

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def method_name_for(user_id: int, name: str) -> str:
    return f"u{int(user_id)}_{name}"


def ensure_user_factors_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_custom_factors (
              id            BIGSERIAL PRIMARY KEY,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name          TEXT NOT NULL,
              method_name   TEXT NOT NULL UNIQUE,
              body          TEXT NOT NULL,
              description   TEXT NOT NULL DEFAULT '',
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (user_id, name)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_custom_factors_user "
            "ON user_custom_factors (user_id, updated_at DESC)"
        )


def resolve_db_user_id(user: dict[str, Any]) -> int:
    """DEV_SKIP_AUTH 的 id=0 不能做外键，落到种子 admin。"""
    uid = int(user.get("id") or 0)
    if uid > 0:
        return uid
    from services.auth.auth_store import get_user_by_username
    from services.core.env_config import env

    username = (env("ADMIN_USERNAME", "admin") or "admin").strip()
    row = get_user_by_username(username)
    if not row:
        raise PermissionError("未找到 admin，无法写入自定义因子")
    return int(row["id"])


def _extract_def_name(body: str) -> str | None:
    m = re.search(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", body or "", flags=re.M)
    return m.group(1) if m else None


def _normalize_body(body: str, name: str, description: str = "") -> str:
    e = (body or "").strip()
    if not e:
        raise ValueError("表达式不能为空")
    doc = (description or name).replace("\\", "\\\\").replace('"""', "'''")
    if not e.lstrip().startswith("def "):
        # 兼容旧数据：仅函数体时自动包一层
        if "return" not in e:
            e = f"return {e}"
        e = f'def {name}(self):\n    """{doc}"""\n    ' + e.replace("\n", "\n    ")
        return e
    def_name = _extract_def_name(e)
    if not def_name:
        raise ValueError("请写完整函数，例如 def RET_5D_DEMO(self): ...")
    if def_name != name:
        raise ValueError(f"因子代码「{name}」须与函数名「{def_name}」一致")
    return e


def _body_as_method(body: str, method_name: str, logical_name: str, description: str) -> str:
    """存库 body 用逻辑名；生成文件时换成物理 method_name。"""
    normalized = _normalize_body(body, logical_name, description)
    return re.sub(
        rf"^def\s+{re.escape(logical_name)}\s*\(",
        f"def {method_name}(",
        normalized,
        count=1,
        flags=re.M,
    )


def _load_index() -> dict:
    with INDEX_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_index(data: dict) -> None:
    data["updated"] = date.today().isoformat()
    libs = data.get("libraries") or {}
    data["total_factors"] = sum(len((lib or {}).get("factors") or []) for lib in libs.values())
    with INDEX_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _list_all_rows() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, name, method_name, body, description,
                   created_at, updated_at
            FROM user_custom_factors
            ORDER BY user_id ASC, name ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def rebuild_custom_lib() -> None:
    """从表全量重写 custom_lib.py 与 index.yaml 的 custom_lib.factors。"""
    rows = _list_all_rows()
    header = (
        '"""自定义因子库（按用户隔离；方法名 = u{user_id}_{name}）。\n\n'
        "研究员在 Web 新增；Postgres 为权威；本文件为同步产物。\n"
        "检测/回测时把方法体发给 YGQuant ResearchEngine。\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from app.services.factor.base import FactorLibrary\n\n\n"
        f"class {CUSTOM_CLASS}(FactorLibrary):\n"
        '    """用户自定义因子。公共库因子在 momentum/value/technical/… 中。"""\n\n'
        '    author = "SVQuant"\n'
    )
    parts = [header]
    factors_meta: list[dict[str, Any]] = []
    for row in rows:
        method = _body_as_method(
            row["body"],
            row["method_name"],
            row["name"],
            row.get("description") or row["name"],
        )
        indented = "\n".join(("    " + ln if ln.strip() else ln) for ln in method.splitlines())
        parts.append("\n" + indented.rstrip() + "\n")
        desc = (row.get("description") or row["name"]).strip()
        factors_meta.append(
            {
                "name": row["name"],
                "method_name": row["method_name"],
                "owner_id": int(row["user_id"]),
                "description": desc,
                "explain": desc,
                "params": {},
                "tags": ["custom"],
            }
        )

    py_path = FACTOR_DIR / CUSTOM_FILE
    py_path.write_text("".join(parts) + "\n", encoding="utf-8")

    index = _load_index()
    libs = index.setdefault("libraries", {})
    custom = libs.setdefault(
        "custom_lib",
        {
            "file": CUSTOM_FILE,
            "class": CUSTOM_CLASS,
            "description": "用户自定义因子（按 owner_id 隔离）",
            "author": "SVQuant",
            "tags": ["custom"],
            "factors": [],
        },
    )
    custom["file"] = CUSTOM_FILE
    custom["class"] = CUSTOM_CLASS
    custom["description"] = "用户自定义因子（按 owner_id 隔离）"
    custom["factors"] = factors_meta
    _save_index(index)


def _extract_method_from_source(source: str, method_name: str) -> str | None:
    lines = source.splitlines()
    start = -1
    indent = ""
    for i, line in enumerate(lines):
        m = re.match(rf"^(\s*)def\s+{re.escape(method_name)}\s*\(", line)
        if m:
            start = i
            indent = m.group(1)
            break
    if start < 0:
        return None
    out = [lines[start]]
    body_indent = indent + "    "
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            out.append(line)
            continue
        if line.startswith(body_indent):
            out.append(line)
            continue
        break
    n = len(indent)
    text = "\n".join(ln[n:] if len(ln) >= n else ln for ln in out).strip()
    # 存库用逻辑名：去掉可能的 u{id}_ 前缀在 def 上——迁移时单独处理
    return text


def migrate_legacy_custom_to_admin() -> dict[str, Any]:
    """把磁盘上尚无归属的自定义方法迁到 admin。"""
    ensure_user_factors_schema()
    from services.auth.auth_store import get_user_by_username, seed_admin
    from services.core.env_config import env

    seed_admin()
    username = (env("ADMIN_USERNAME", "admin") or "admin").strip()
    admin = get_user_by_username(username)
    if not admin:
        return {"ok": False, "migrated": 0, "error": "no admin"}
    admin_id = int(admin["id"])

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) AS c FROM user_custom_factors"
        ).fetchone()["c"]
    if existing:
        rebuild_custom_lib()
        return {"ok": True, "migrated": 0, "skipped": "table_not_empty"}

    py_path = FACTOR_DIR / CUSTOM_FILE
    if not py_path.exists():
        rebuild_custom_lib()
        return {"ok": True, "migrated": 0}

    src = py_path.read_text(encoding="utf-8")
    index = _load_index()
    custom = (index.get("libraries") or {}).get("custom_lib") or {}
    entries = list(custom.get("factors") or [])
    if not entries:
        # 从源码扫 def
        for m in re.finditer(r"^    def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", src, flags=re.M):
            entries.append({"name": m.group(1), "description": m.group(1)})

    migrated = 0
    with get_conn() as conn:
        for entry in entries:
            logical = str(entry.get("name") or "").strip()
            if not logical or not NAME_RE.match(logical):
                continue
            # 已是命名空间则拆出
            owner_id = admin_id
            name = logical
            m = re.match(r"^u(\d+)_(.+)$", logical)
            if m:
                owner_id = int(m.group(1)) or admin_id
                name = m.group(2)
            method_physical = method_name_for(owner_id, name)
            raw_method = _extract_method_from_source(src, logical) or _extract_method_from_source(
                src, method_physical
            )
            if not raw_method:
                continue
            # 规范化为逻辑名 def
            body = re.sub(
                r"^def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(",
                f"def {name}(",
                raw_method,
                count=1,
                flags=re.M,
            )
            desc = str(entry.get("description") or entry.get("explain") or name).strip()
            conn.execute(
                """
                INSERT INTO user_custom_factors (user_id, name, method_name, body, description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, name) DO NOTHING
                """,
                (owner_id, name, method_name_for(owner_id, name), body, desc),
            )
            migrated += 1

    rebuild_custom_lib()
    return {"ok": True, "migrated": migrated}


def list_user_factors(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT name, method_name, body, description, created_at, updated_at
            FROM user_custom_factors
            WHERE user_id = %s
            ORDER BY name ASC
            """,
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("created_at", "updated_at"):
            if d.get(k) is not None:
                d[k] = d[k].isoformat()
        out.append(d)
    return out


def get_user_factor(user_id: int, name: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT name, method_name, body, description, created_at, updated_at
            FROM user_custom_factors
            WHERE user_id = %s AND name = %s
            """,
            (user_id, name),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for k in ("created_at", "updated_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


def add_user_factor(
    user_id: int, *, name: str, body: str, description: str = ""
) -> dict[str, Any]:
    name = (name or "").strip()
    if not NAME_RE.match(name):
        raise ValueError("因子名须为合法标识符")
    if name.startswith("u") and re.match(r"^u\d+_", name):
        raise ValueError("因子名请勿使用 u{数字}_ 前缀（系统保留）")
    desc = (description or name).strip()
    normalized = _normalize_body(body, name, desc)
    mname = method_name_for(user_id, name)
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM user_custom_factors WHERE user_id = %s AND name = %s",
            (user_id, name),
        ).fetchone()
        if exists:
            raise ValueError(f"已存在: {name}")
        global_hit = conn.execute(
            "SELECT 1 FROM user_custom_factors WHERE method_name = %s",
            (mname,),
        ).fetchone()
        if global_hit:
            raise ValueError(f"物理方法名冲突: {mname}")
        conn.execute(
            """
            INSERT INTO user_custom_factors (user_id, name, method_name, body, description)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, name, mname, normalized, desc),
        )
    rebuild_custom_lib()
    return {"ok": True, "name": name, "method_name": mname, "owner_id": user_id}


def update_user_factor(
    user_id: int, *, name: str, body: str, description: str = ""
) -> dict[str, Any]:
    name = (name or "").strip()
    if not NAME_RE.match(name):
        raise ValueError("因子名须为合法标识符")
    desc = (description or name).strip()
    normalized = _normalize_body(body, name, desc)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, method_name FROM user_custom_factors WHERE user_id = %s AND name = %s",
            (user_id, name),
        ).fetchone()
        if not row:
            raise KeyError(name)
        conn.execute(
            """
            UPDATE user_custom_factors
            SET body = %s, description = %s, updated_at = NOW()
            WHERE user_id = %s AND name = %s
            """,
            (normalized, desc, user_id, name),
        )
        mname = row["method_name"]
    rebuild_custom_lib()
    return {"ok": True, "name": name, "method_name": mname, "owner_id": user_id}


def delete_user_factor(user_id: int, name: str) -> dict[str, Any]:
    name = (name or "").strip()
    with get_conn() as conn:
        row = conn.execute(
            "DELETE FROM user_custom_factors WHERE user_id = %s AND name = %s RETURNING name",
            (user_id, name),
        ).fetchone()
        if not row:
            raise KeyError(name)
    rebuild_custom_lib()
    return {"ok": True, "name": name}


def filtered_index_yaml(owner_id: int | None) -> str:
    """公共库全量；custom_lib 仅当前用户（未登录则空）。缺 factors 的库自动展开。"""
    from services.factor.factor_catalog_expand import expand_index

    index = expand_index(_load_index())
    libs = index.get("libraries") or {}
    custom = libs.get("custom_lib")
    if custom is not None:
        factors = list(custom.get("factors") or [])
        if owner_id is None:
            custom = {**custom, "factors": []}
        else:
            custom = {
                **custom,
                "factors": [f for f in factors if int(f.get("owner_id") or -1) == int(owner_id)],
            }
        libs = {**libs, "custom_lib": custom}
        index = {**index, "libraries": libs}
        index["total_factors"] = sum(
            len((lib or {}).get("factors") or []) for lib in libs.values()
        )
    return yaml.safe_dump(index, allow_unicode=True, sort_keys=False)


def custom_lib_source_for_user(owner_id: int | None) -> str:
    """仅含当前用户方法的 CustomLib 源码（未登录则空类）。"""
    header = (
        '"""自定义因子（仅当前用户可见片段）。"""\n\n'
        "from __future__ import annotations\n\n"
        "from app.services.factor.base import FactorLibrary\n\n\n"
        f"class {CUSTOM_CLASS}(FactorLibrary):\n"
        '    author = "SVQuant"\n'
    )
    if owner_id is None:
        return header + "\n"
    rows = []
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT name, method_name, body, description
            FROM user_custom_factors WHERE user_id = %s ORDER BY name
            """,
            (owner_id,),
        ).fetchall()
    parts = [header]
    for row in rows:
        method = _body_as_method(
            row["body"],
            row["method_name"],
            row["name"],
            row.get("description") or row["name"],
        )
        indented = "\n".join(("    " + ln if ln.strip() else ln) for ln in method.splitlines())
        parts.append("\n" + indented.rstrip() + "\n")
    return "".join(parts) + "\n"
