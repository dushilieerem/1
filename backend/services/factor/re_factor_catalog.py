# -*- coding: utf-8 -*-
"""ResearchEngine 官方因子目录：PostgreSQL 为权威缓存。

默认读库（毫秒）；同步脚本 / ?fresh=1 才拉 RE。
有变更才写库；无变更只记 sync 日志时间。
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from services.core.db import get_conn
from services.core.re_config import RE_BASE
PRIMARY_LIBS = frozenset(
    {
        "momentum_lib",
        "value_lib",
        "technical_lib",
        "volatility_lib",
        "trading_lib",
        "classic_indicators",
        "emotion_indicators",
        "risk_indicators",
        "technical_indicators",
        "alpha_features",
        # 同事新主库（单库 + category_id SV01–SV15）
        "主因子库",
    }
)

# RE 因子 category_id → 中文分类（接口有 category_name 时优先用接口）
CATEGORY_ID_LABELS: dict[str, str] = {
    "SV01": "动量因子",
    "SV02": "技术复合因子",
    "SV03": "Beta因子",
    "SV04": "区间与通道因子",
    "SV05": "技术复合因子",
    "SV06": "流动性因子",
    "SV07": "资金流与量能因子",
    "SV08": "量价关系因子",
    "SV09": "日内结构因子",
    "SV10": "波动率因子",
    "SV11": "估值因子",
    "SV12": "规模因子",
    "SV13": "风险分布因子",
    "SV14": "待复核",
    "SV15": "标签与不可交易",
}

_lock = threading.Lock()
# 按 scope 分缓存，避免 primary≈738 覆盖 all≈1043（刷新后变回七百多）
_cache_by_scope: dict[str, dict[str, Any]] = {}
_schema_ready = False


def ensure_re_factor_catalog_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS re_factor_catalog_snapshot (
              scope TEXT PRIMARY KEY,
              content_hash TEXT NOT NULL,
              payload JSONB NOT NULL,
              fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              fetched_at_unix DOUBLE PRECISION NOT NULL,
              factor_count INT NOT NULL DEFAULT 0,
              library_count INT NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS re_factor_catalog_sync_log (
              id BIGSERIAL PRIMARY KEY,
              scope TEXT NOT NULL,
              changed BOOLEAN NOT NULL,
              content_hash TEXT,
              factor_count INT,
              message TEXT,
              detail JSONB,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # 旧库补列（P1-F04：记录变更 diff）
        conn.execute(
            """
            ALTER TABLE re_factor_catalog_sync_log
            ADD COLUMN IF NOT EXISTS detail JSONB
            """
        )
    _schema_ready = True


def _scope(include_all: bool) -> str:
    return "all" if include_all else "primary"


def _get_json(path: str, timeout: float = 45.0) -> Any:
    url = f"{RE_BASE}{path}"
    req = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _category_label(category_id: str | None, lib_tags: list[Any]) -> str | None:
    cid = str(category_id or "").strip().upper()
    if not cid:
        return None
    if cid in CATEGORY_ID_LABELS:
        return CATEGORY_ID_LABELS[cid]
    # 兜底：SV01→tags[0]（若 tags 正好 15 个且顺序一致）
    if cid.startswith("SV") and cid[2:].isdigit() and len(lib_tags) >= int(cid[2:]):
        idx = int(cid[2:]) - 1
        tag = str(lib_tags[idx] or "").strip()
        if tag:
            return tag
    return cid


def _factors_for_lib(lib: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str | None]:
    name = str(lib.get("name") or "").strip()
    if not name:
        return "", [], None
    lib_tags = list(lib.get("tags") or [])
    try:
        detail = _get_json(f"/api/factors/{urllib.parse.quote(name)}")
        rows: list[dict[str, Any]] = []
        for f in detail.get("factors") or []:
            fname = str(f.get("name") or "").strip()
            if not fname:
                continue
            desc = (f.get("description") or fname or "").strip() or fname
            category_id = str(f.get("category_id") or "").strip() or None
            category_name = str(f.get("category_name") or "").strip() or None
            display_name = str(f.get("display_name") or "").strip() or None
            factor_id = str(f.get("factor_id") or fname).strip() or fname
            name_en = str(f.get("name_en") or "").strip() or None
            cat_label = category_name or _category_label(category_id, lib_tags)
            rows.append(
                {
                    "name": fname,
                    "description": desc,
                    "library": name,
                    "library_description": lib.get("description"),
                    "tags": lib_tags,
                    "category_id": category_id,
                    "category_name": category_name,
                    "category_label": cat_label,
                    "factor_id": factor_id,
                    "display_name": display_name,
                    "name_en": name_en,
                }
            )
        return name, rows, None
    except Exception as e:  # noqa: BLE001
        return name, [], f"{name}: {e}"


def content_hash(libraries: list[dict[str, Any]], factors: list[dict[str, Any]]) -> str:
    """库名 + 因子名 + 描述；用于判断同事侧是否有更新。"""
    lines: list[str] = []
    for lib in sorted(libraries, key=lambda x: str(x.get("name") or "")):
        lines.append(
            f"L|{lib.get('name')}|{lib.get('description')}|{json.dumps(lib.get('tags') or [], ensure_ascii=False, sort_keys=True)}"
        )
    for f in sorted(
        factors,
        key=lambda x: (str(x.get("library") or ""), str(x.get("name") or "")),
    ):
        lines.append(
            f"F|{f.get('library')}|{f.get('name')}|{f.get('description')}|"
            f"{f.get('category_id')}|{f.get('category_label')}|"
            f"{json.dumps(f.get('tags') or [], ensure_ascii=False, sort_keys=True)}"
        )
    raw = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _factor_key(f: dict[str, Any]) -> str:
    return f"{f.get('library') or ''}::{f.get('name') or ''}"


def factor_diff(
    old: dict[str, Any] | None, new: dict[str, Any], *, limit: int = 50
) -> dict[str, Any]:
    """两次同步之间的因子增删 diff（P1-F04）。

    以「库名::因子名」为键；首次同步没有旧快照，不算 diff。
    """
    if old is None:
        return {
            "first_sync": True,
            "added_count": len(new.get("factors") or []),
            "removed_count": 0,
            "added": [],
            "removed": [],
            "truncated": False,
        }
    old_keys = {_factor_key(f) for f in old.get("factors") or []}
    new_keys = {_factor_key(f) for f in new.get("factors") or []}
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    return {
        "first_sync": False,
        "added_count": len(added),
        "removed_count": len(removed),
        "added": added[:limit],
        "removed": removed[:limit],
        "truncated": len(added) > limit or len(removed) > limit,
    }


def _pull_from_re(*, include_all: bool = False) -> dict[str, Any]:
    t0 = time.time()
    lib_payload = _get_json("/api/factor-libraries")
    libraries = list(lib_payload.get("libraries") or [])
    if not include_all:
        libraries = [x for x in libraries if str(x.get("name") or "") in PRIMARY_LIBS]

    factors: list[dict[str, Any]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(libraries)))) as pool:
        futs = [pool.submit(_factors_for_lib, lib) for lib in libraries]
        for fut in as_completed(futs):
            _name, rows, err = fut.result()
            if err:
                errors.append(err)
            factors.extend(rows)

    factors.sort(key=lambda x: (str(x.get("library") or ""), str(x.get("name") or "")))
    now = time.time()
    h = content_hash(libraries, factors)
    return {
        "ok": True,
        "libraries": libraries,
        "factors": factors,
        "errors": errors,
        "include_all": include_all,
        "elapsed_ms": int((now - t0) * 1000),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        "fetched_at_unix": now,
        "re_base": RE_BASE,
        "source": "re",
        "factor_count": len(factors),
        "library_count": len(libraries),
        "content_hash": h,
    }


def _load_db(include_all: bool) -> dict[str, Any] | None:
    ensure_re_factor_catalog_schema()
    scope = _scope(include_all)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT content_hash, payload, fetched_at, fetched_at_unix,
                   factor_count, library_count
            FROM re_factor_catalog_snapshot
            WHERE scope = %s
            """,
            (scope,),
        ).fetchone()
    if not row:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict) or not payload.get("factors"):
        return None
    out = dict(payload)
    out["ok"] = True
    out["source"] = "db"
    out["content_hash"] = row["content_hash"]
    out["factor_count"] = row["factor_count"] or len(out.get("factors") or [])
    out["library_count"] = row["library_count"] or len(out.get("libraries") or [])
    if row["fetched_at_unix"]:
        out["fetched_at_unix"] = float(row["fetched_at_unix"])
    if row["fetched_at"]:
        out["fetched_at"] = row["fetched_at"].strftime("%Y-%m-%dT%H:%M:%S")
    return out


def _save_db(
    payload: dict[str, Any],
    *,
    changed: bool,
    message: str,
    diff: dict[str, Any] | None = None,
) -> None:
    ensure_re_factor_catalog_schema()
    scope = _scope(bool(payload.get("include_all")))
    h = str(payload.get("content_hash") or "")
    factor_count = int(payload.get("factor_count") or len(payload.get("factors") or []))
    library_count = int(payload.get("library_count") or len(payload.get("libraries") or []))
    fetched_at_unix = float(payload.get("fetched_at_unix") or time.time())
    # payload 里不要循环引用；存精简字段
    store = {
        "ok": True,
        "libraries": payload.get("libraries") or [],
        "factors": payload.get("factors") or [],
        "errors": payload.get("errors") or [],
        "include_all": bool(payload.get("include_all")),
        "elapsed_ms": payload.get("elapsed_ms"),
        "fetched_at": payload.get("fetched_at"),
        "fetched_at_unix": fetched_at_unix,
        "re_base": payload.get("re_base") or RE_BASE,
        "factor_count": factor_count,
        "library_count": library_count,
        "content_hash": h,
    }
    with get_conn() as conn:
        if changed:
            conn.execute(
                """
                INSERT INTO re_factor_catalog_snapshot (
                  scope, content_hash, payload, fetched_at, fetched_at_unix,
                  factor_count, library_count, updated_at
                ) VALUES (
                  %s, %s, %s::jsonb, to_timestamp(%s), %s, %s, %s, NOW()
                )
                ON CONFLICT (scope) DO UPDATE SET
                  content_hash = EXCLUDED.content_hash,
                  payload = EXCLUDED.payload,
                  fetched_at = EXCLUDED.fetched_at,
                  fetched_at_unix = EXCLUDED.fetched_at_unix,
                  factor_count = EXCLUDED.factor_count,
                  library_count = EXCLUDED.library_count,
                  updated_at = NOW()
                """,
                (
                    scope,
                    h,
                    json.dumps(store, ensure_ascii=False),
                    fetched_at_unix,
                    fetched_at_unix,
                    factor_count,
                    library_count,
                ),
            )
        else:
            # 无变更：只碰 sync 时间戳，方便看「上次检查」
            conn.execute(
                """
                UPDATE re_factor_catalog_snapshot
                SET updated_at = NOW()
                WHERE scope = %s
                """,
                (scope,),
            )
        conn.execute(
            """
            INSERT INTO re_factor_catalog_sync_log (
              scope, changed, content_hash, factor_count, message, detail
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                scope,
                changed,
                h,
                factor_count,
                message,
                json.dumps(diff, ensure_ascii=False) if diff else None,
            ),
        )


def sync_from_re(*, include_all: bool = False) -> dict[str, Any]:
    """拉 RE → 比 hash → 有变更写库。返回结果含 changed / message。"""
    ensure_re_factor_catalog_schema()
    pulled = _pull_from_re(include_all=include_all)
    old = _load_db(include_all)
    old_hash = (old or {}).get("content_hash")
    new_hash = pulled.get("content_hash")
    changed = old_hash != new_hash
    diff = factor_diff(old, pulled)

    if changed or old is None:
        if old:
            msg = (
                f"已更新：{old.get('factor_count')} → {pulled.get('factor_count')} 个因子"
                f"（新增 {diff['added_count']} / 移除 {diff['removed_count']}）"
            )
        else:
            msg = f"首次写入 {pulled.get('factor_count')} 个因子"
        _save_db(pulled, changed=True, message=msg, diff=diff)
        result = dict(pulled)
        result["changed"] = True
        result["message"] = msg
        result["diff"] = diff
    else:
        msg = f"无变更（hash={str(new_hash)[:12]}…，{pulled.get('factor_count')} 个）"
        _save_db(old, changed=False, message=msg)
        result = dict(old)
        result["changed"] = False
        result["message"] = msg
        result["last_check_elapsed_ms"] = pulled.get("elapsed_ms")

    result["source"] = "db"
    scope = _scope(include_all)
    with _lock:
        mem = dict(result)
        mem["source"] = "memory"
        _cache_by_scope[scope] = mem
    out = dict(result)
    out["source"] = "re-sync"
    return out


def catalog_scope_status() -> dict[str, Any]:
    """P0-14：primary/all 双 scope 的一致性/陈旧检查。"""
    out: dict[str, Any] = {"ok": True, "scopes": {}, "warnings": []}
    now = time.time()
    for scope, flag in (("primary", False), ("all", True)):
        snap = _load_db(flag)
        if not snap:
            out["ok"] = False
            out["warnings"].append(f"{scope} 未同步")
            out["scopes"][scope] = None
            continue
        fetched = int(snap.get("fetched_at_unix") or 0)
        age_hours = round((now - fetched) / 3600, 1) if fetched else None
        out["scopes"][scope] = {
            "factor_count": len(snap.get("factors") or []),
            "content_hash": snap.get("content_hash"),
            "fetched_at": snap.get("fetched_at"),
            "age_hours": age_hours,
        }
        if age_hours is not None and age_hours > 24 * 7:
            out["warnings"].append(f"{scope} 已 {age_hours} 小时未同步")
    pri = out["scopes"].get("primary")
    alls = out["scopes"].get("all")
    if pri and alls and int(pri["factor_count"]) > int(alls["factor_count"]):
        out["ok"] = False
        out["warnings"].append("primary 因子数大于 all，scope 可能写反")
    if out["warnings"]:
        out["ok"] = False
    return out


def sync_log(limit: int = 20) -> list[dict[str, Any]]:
    """最近的同步记录（含 diff），供管理后台诊断（P1-F04）。"""
    ensure_re_factor_catalog_schema()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT scope, changed, content_hash, factor_count, message, detail, created_at
            FROM re_factor_catalog_sync_log
            ORDER BY id DESC
            LIMIT %s
            """,
            (max(1, min(200, int(limit))),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        created = item.get("created_at")
        if created is not None:
            item["created_at"] = created.isoformat()
        out.append(item)
    return out


def catalog_sync_status(limit: int = 20) -> dict[str, Any]:
    """P1-F04：双 scope 一致性 + 陈旧告警 + 最近同步 diff。"""
    status = catalog_scope_status()
    status["recent_syncs"] = sync_log(limit)
    return status


def sync_all_scopes() -> dict[str, Any]:
    """同一周期刷新 primary 与 all，并返回一致性检查（P0-14）。"""
    errors: list[str] = []
    primary: dict[str, Any] | None = None
    all_scope: dict[str, Any] | None = None
    try:
        primary = sync_from_re(include_all=False)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"primary: {exc}")
    try:
        all_scope = sync_from_re(include_all=True)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"all: {exc}")
    status = catalog_scope_status()
    return {
        "ok": not errors and bool(primary) and bool(all_scope) and status.get("ok", False),
        "primary": primary,
        "all": all_scope,
        "consistency": status,
        "errors": errors,
    }


def fetch_re_catalog(*, force: bool = False, include_all: bool = False) -> dict[str, Any]:
    """页面默认读内存/PG；force 才同步 RE。"""
    ensure_re_factor_catalog_schema()
    scope = _scope(include_all)

    if force:
        return sync_from_re(include_all=include_all)

    with _lock:
        cached = _cache_by_scope.get(scope)
        if cached is not None and cached.get("factors"):
            hit = dict(cached)
            hit["source"] = hit.get("source") or "memory"
            return hit

    db = _load_db(include_all)
    if db is not None:
        with _lock:
            _cache_by_scope[scope] = db
        return db

    # 全库尚未同步过：回退 primary 只作只读返回，不写入 all 槽位
    if include_all:
        primary = _load_db(False)
        if primary is not None:
            with _lock:
                _cache_by_scope.setdefault("primary", primary)
            return primary

    # 库空：阻塞拉一次，避免页面空白
    return sync_from_re(include_all=include_all)


def clear_re_catalog_cache() -> None:
    with _lock:
        _cache_by_scope.clear()


def warm_re_catalog_async() -> None:
    """启动：优先载入 PG；库空则后台同步 RE。"""

    def _run() -> None:
        try:
            ensure_re_factor_catalog_schema()
            # 优先全库快照（与页面 / 夜间 --all 对齐）；没有再回退 primary
            all_db = _load_db(True)
            pri_db = _load_db(False)
            with _lock:
                if all_db is not None:
                    _cache_by_scope["all"] = all_db
                if pri_db is not None:
                    _cache_by_scope["primary"] = pri_db
            status = catalog_scope_status()
            if all_db is not None and status.get("ok"):
                n = len(all_db.get("factors") or [])
                print(f"  re-catalog 已从 PostgreSQL 载入全库 {n} 个因子")
                return
            if pri_db is not None:
                n = len(pri_db.get("factors") or [])
                print(f"  re-catalog 仅有 primary {n} 个，后台补全库…")
            else:
                print("  re-catalog 库空，后台首次同步 RE（全库）…")
            out = sync_all_scopes()
            primary_msg = ((out.get("primary") or {}).get("message") or "")
            all_msg = ((out.get("all") or {}).get("message") or "")
            print(f"  re-catalog 同步完成：primary={primary_msg} / all={all_msg}")
        except Exception as exc:  # noqa: BLE001
            print(f"  re-catalog 预热失败: {exc}")

    threading.Thread(target=_run, name="re-catalog-warm", daemon=True).start()
