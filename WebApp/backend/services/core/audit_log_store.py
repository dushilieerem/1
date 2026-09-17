# -*- coding: utf-8 -*-
"""平台审计日志（管理员可查：谁、何时、调了什么、结果如何）。"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from services.core.db import get_conn

# 同类 5xx 短时只记一条，避免 RE 宕机时 market-data 等刷屏
_DEDUP_WINDOW_SEC = 60.0
_recent_5xx: dict[str, float] = {}


def _should_skip_dup_5xx(
    method: str | None,
    path: str | None,
    status_code: int | None,
) -> bool:
    if status_code is None or status_code < 500:
        return False
    key = f"{(method or '').upper()} {(path or '').split('?', 1)[0]}"
    now = time.monotonic()
    # 顺带清过期项，避免字典无限涨
    stale = [k for k, t in _recent_5xx.items() if now - t > _DEDUP_WINDOW_SEC]
    for k in stale:
        _recent_5xx.pop(k, None)
    last = _recent_5xx.get(key)
    if last is not None and now - last < _DEDUP_WINDOW_SEC:
        return True
    _recent_5xx[key] = now
    return False

_MODULE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("/api/auth", "auth"),
    ("/api/profile", "auth"),
    ("/api/users", "auth"),
    ("/api/kh", "kh"),
    ("/api/community", "community"),
    ("/api/factor", "factor"),
    ("/api/strategy", "strategy"),
    ("/api/detect", "detect"),
    ("/api/agent", "agent"),
    ("/api/ai", "ai"),
    ("/api/news", "news"),
    ("/api/watchlists", "watchlists"),
    # 行情 / 回测走 RE 网关，与 /api/re 同归 re
    ("/api/market-data", "re"),
    ("/api/backtest", "re"),
    ("/api/re", "re"),
    ("/api/admin", "admin"),
)


def ensure_audit_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_audit_logs (
              id            BIGSERIAL PRIMARY KEY,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              user_id       BIGINT,
              username      TEXT,
              role          TEXT,
              action        TEXT NOT NULL,
              module        TEXT,
              resource      TEXT,
              method        TEXT,
              path          TEXT,
              status_code   INTEGER,
              duration_ms   INTEGER,
              ip            TEXT,
              user_agent    TEXT,
              detail        TEXT,
              request_id    TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_audit_logs_created "
            "ON app_audit_logs (created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_audit_logs_user "
            "ON app_audit_logs (user_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_audit_logs_module "
            "ON app_audit_logs (module, created_at DESC)"
        )


def infer_module(path: str) -> str:
    p = (path or "").split("?", 1)[0]
    for prefix, mod in _MODULE_PREFIXES:
        if p.startswith(prefix):
            return mod
    if p.startswith("/api/"):
        return "api"
    return "other"


def infer_action(method: str | None, path: str | None) -> str:
    """把常见业务路径落到可读 action；未命中则回退 http.get / http.post。"""
    m = (method or "GET").upper()
    p = (path or "").split("?", 1)[0]

    if "/favorite" in p and m in ("POST", "DELETE"):
        return "community.favorite"
    if "/like" in p and m in ("POST", "DELETE"):
        return "community.like"
    if m == "POST" and (
        p == "/api/community/posts" or p.rstrip("/").endswith("/api/community/posts")
    ):
        return "community.post_create"
    if m == "DELETE" and p.startswith("/api/community/posts/"):
        return "community.post_delete"
    if m == "POST" and p.startswith("/api/community/comments"):
        return "community.comment"

    # (方法集合或 None=任意, 路径前缀, action)
    prefix_rules: tuple[tuple[set[str] | None, str, str], ...] = (
        ({"GET"}, "/api/market-data/daily", "re.daily_get"),
        ({"GET"}, "/api/market-data/indices", "re.indices_get"),
        ({"GET"}, "/api/market-data/symbols", "re.symbols_get"),
        ({"GET"}, "/api/market-data", "re.market_get"),
        (None, "/api/backtest", "re.backtest"),
        (None, "/api/re/", "re.gateway"),
        (None, "/api/factor", "factor.api"),
        (None, "/api/strategy", "strategy.api"),
        (None, "/api/detect", "detect.api"),
        (None, "/api/kh", "kh.api"),
        (None, "/api/watchlists", "watchlists.api"),
        (None, "/api/news", "news.api"),
        (None, "/api/agent", "agent.api"),
        (None, "/api/ai", "ai.api"),
        (None, "/api/admin", "admin.api"),
    )
    for methods, prefix, action in prefix_rules:
        if methods is not None and m not in methods:
            continue
        if p.startswith(prefix):
            return action
    return f"http.{m.lower()}"


def _clip(s: str | None, n: int) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    return t if len(t) <= n else t[: n - 1] + "…"


def write_audit(
    *,
    action: str,
    user_id: int | None = None,
    username: str | None = None,
    role: str | None = None,
    module: str | None = None,
    resource: str | None = None,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    duration_ms: int | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: str | None = None,
    request_id: str | None = None,
) -> None:
    """写入一条审计记录；失败时静默，不影响主流程。"""
    try:
        path_clean = _clip((path or "").split("?", 1)[0], 240)
        if _should_skip_dup_5xx(method, path_clean, status_code):
            return
        ensure_audit_schema()
        mod = module or (infer_module(path_clean or "") if path_clean else None)
        uid = int(user_id) if user_id is not None else None
        uname = _clip(username, 64)
        # 未登录或未带令牌：统一记「游客」，避免管理页用户列空白
        if uid is None and not uname:
            uname = "游客"
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO app_audit_logs
                  (user_id, username, role, action, module, resource,
                   method, path, status_code, duration_ms, ip, user_agent,
                   detail, request_id)
                VALUES
                  (%s, %s, %s, %s, %s, %s,
                   %s, %s, %s, %s, %s, %s,
                   %s, %s)
                """,
                (
                    uid,
                    uname,
                    _clip(role, 32),
                    _clip(action, 64) or "unknown",
                    _clip(mod, 32),
                    _clip(resource, 240),
                    _clip(method, 16),
                    path_clean,
                    int(status_code) if status_code is not None else None,
                    int(duration_ms) if duration_ms is not None else None,
                    _clip(ip, 64),
                    _clip(user_agent, 240),
                    _clip(detail, 500),
                    _clip(request_id, 64),
                ),
            )
    except Exception as exc:
        print(f"[audit] write skipped: {exc}")


def _row(r: dict[str, Any]) -> dict[str, Any]:
    created = r.get("created_at")
    if isinstance(created, datetime):
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        created_s = created.isoformat()
    else:
        created_s = str(created) if created else None
    return {
        "id": int(r["id"]),
        "createdAt": created_s,
        "userId": int(r["user_id"]) if r.get("user_id") is not None else None,
        "username": r.get("username") or None,
        "role": r.get("role") or None,
        "action": r.get("action") or "",
        "module": r.get("module") or None,
        "resource": r.get("resource") or None,
        "method": r.get("method") or None,
        "path": r.get("path") or None,
        "statusCode": int(r["status_code"]) if r.get("status_code") is not None else None,
        "durationMs": int(r["duration_ms"]) if r.get("duration_ms") is not None else None,
        "ip": r.get("ip") or None,
        "detail": r.get("detail") or None,
        "requestId": r.get("request_id") or None,
    }


def purge_audit_logs(*, days: int) -> int:
    """删除早于 N 天的审计记录；days<=0 表示不清理。返回删除行数。"""
    days = int(days)
    if days <= 0:
        return 0
    ensure_audit_schema()
    with get_conn() as conn:
        cur = conn.execute(
            """
            DELETE FROM app_audit_logs
            WHERE created_at < NOW() - (%s * INTERVAL '1 day')
            """,
            (days,),
        )
        # psycopg / 驱动：rowcount
        return int(getattr(cur, "rowcount", 0) or 0)


def list_audit_logs(
    *,
    limit: int = 50,
    offset: int = 0,
    module: str | None = None,
    username: str | None = None,
    action: str | None = None,
    status_code: int | None = None,
    status_min: int | None = None,
    status_max: int | None = None,
    method: str | None = None,
    write_only: bool = False,
    path_contains: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    ensure_audit_schema()
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    where: list[str] = []
    args: list[Any] = []
    if module and module.strip():
        where.append("module = %s")
        args.append(module.strip())
    if username and username.strip():
        where.append("username ILIKE %s")
        args.append(f"%{username.strip()}%")
    if action and action.strip():
        where.append("action ILIKE %s")
        args.append(f"%{action.strip()}%")
    if status_code is not None:
        where.append("status_code = %s")
        args.append(int(status_code))
    if status_min is not None:
        where.append("status_code >= %s")
        args.append(int(status_min))
    if status_max is not None:
        where.append("status_code <= %s")
        args.append(int(status_max))
    if method and method.strip():
        where.append("UPPER(COALESCE(method, '')) = %s")
        args.append(method.strip().upper())
    if write_only:
        # %%：避免 psycopg 把 ILIKE 通配符当成参数占位
        where.append(
            "("
            "UPPER(COALESCE(method, '')) IN ('POST', 'PUT', 'PATCH', 'DELETE') "
            "OR action ILIKE 'auth.%%'"
            ")"
        )
    if path_contains and path_contains.strip():
        where.append("path ILIKE %s")
        args.append(f"%{path_contains.strip()}%")
    if since and since.strip():
        where.append("created_at >= %s::timestamptz")
        args.append(since.strip())
    if until and until.strip():
        where.append("created_at <= %s::timestamptz")
        args.append(until.strip())
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM app_audit_logs{clause}", args
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT * FROM app_audit_logs
            {clause}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            [*args, limit, offset],
        ).fetchall()
    return {
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "items": [_row(dict(r)) for r in rows],
    }
