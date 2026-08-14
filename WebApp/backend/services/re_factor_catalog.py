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

from services.db import get_conn

RE_BASE = os.environ.get("YG_RE_BASE", "http://192.168.3.64:9527").rstrip("/")
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
    }
)

_lock = threading.Lock()
_cache: dict[str, Any] | None = None
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
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
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


def _factors_for_lib(lib: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str | None]:
    name = str(lib.get("name") or "").strip()
    if not name:
        return "", [], None
    try:
        detail = _get_json(f"/api/factors/{urllib.parse.quote(name)}")
        rows: list[dict[str, Any]] = []
        for f in detail.get("factors") or []:
            fname = str(f.get("name") or "").strip()
            if not fname:
                continue
            desc = (f.get("description") or fname or "").strip() or fname
            rows.append(
                {
                    "name": fname,
                    "description": desc,
                    "library": name,
                    "library_description": lib.get("description"),
                    "tags": lib.get("tags") or [],
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
            f"F|{f.get('library')}|{f.get('name')}|{f.get('description')}|{json.dumps(f.get('tags') or [], ensure_ascii=False, sort_keys=True)}"
        )
    raw = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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


def _save_db(payload: dict[str, Any], *, changed: bool, message: str) -> None:
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
              scope, changed, content_hash, factor_count, message
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (scope, changed, h, factor_count, message),
        )


def sync_from_re(*, include_all: bool = False) -> dict[str, Any]:
    """拉 RE → 比 hash → 有变更写库。返回结果含 changed / message。"""
    global _cache
    ensure_re_factor_catalog_schema()
    pulled = _pull_from_re(include_all=include_all)
    old = _load_db(include_all)
    old_hash = (old or {}).get("content_hash")
    new_hash = pulled.get("content_hash")
    changed = old_hash != new_hash

    if changed or old is None:
        msg = (
            f"已更新：{old.get('factor_count') if old else 0} → {pulled.get('factor_count')} 个因子"
            if old
            else f"首次写入 {pulled.get('factor_count')} 个因子"
        )
        _save_db(pulled, changed=True, message=msg)
        result = dict(pulled)
        result["changed"] = True
        result["message"] = msg
    else:
        msg = f"无变更（hash={str(new_hash)[:12]}…，{pulled.get('factor_count')} 个）"
        _save_db(old, changed=False, message=msg)
        result = dict(old)
        result["changed"] = False
        result["message"] = msg
        result["last_check_elapsed_ms"] = pulled.get("elapsed_ms")

    result["source"] = "db"
    with _lock:
        mem = dict(result)
        mem["source"] = "memory"
        _cache = mem
    out = dict(result)
    out["source"] = "re-sync"
    return out


def fetch_re_catalog(*, force: bool = False, include_all: bool = False) -> dict[str, Any]:
    """页面默认读内存/PG；force 才同步 RE。"""
    global _cache
    ensure_re_factor_catalog_schema()

    if force:
        return sync_from_re(include_all=include_all)

    with _lock:
        if (
            _cache is not None
            and bool(_cache.get("include_all")) == include_all
            and _cache.get("factors")
        ):
            hit = dict(_cache)
            hit["source"] = hit.get("source") or "memory"
            return hit
        # 请求全库但内存里是 primary：也先用着，避免空白
        if (
            include_all
            and _cache is not None
            and _cache.get("factors")
            and not bool(_cache.get("include_all"))
        ):
            hit = dict(_cache)
            hit["source"] = hit.get("source") or "memory"
            return hit

    db = _load_db(include_all)
    if db is not None:
        with _lock:
            _cache = db
        return db

    # 全库尚未同步过：回退 primary，勿在普通浏览时阻塞拉 RE
    if include_all:
        primary = _load_db(False)
        if primary is not None:
            with _lock:
                _cache = primary
            return primary

    # 库空：阻塞拉一次，避免页面空白
    return sync_from_re(include_all=include_all)


def clear_re_catalog_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def warm_re_catalog_async() -> None:
    """启动：优先载入 PG；库空则后台同步 RE。"""

    def _run() -> None:
        global _cache
        try:
            ensure_re_factor_catalog_schema()
            # 优先全库快照（与页面 / 夜间 --all 对齐）；没有再回退 primary
            db = _load_db(True) or _load_db(False)
            if db is not None:
                with _lock:
                    _cache = db
                n = len(db.get("factors") or [])
                print(f"  re-catalog 已从 PostgreSQL 载入 {n} 个因子")
                return
            print("  re-catalog 库空，后台首次同步 RE（全库）…")
            out = sync_from_re(include_all=True)
            print(f"  re-catalog 同步完成：{out.get('message')}")
        except Exception as exc:  # noqa: BLE001
            print(f"  re-catalog 预热失败: {exc}")

    threading.Thread(target=_run, name="re-catalog-warm", daemon=True).start()
