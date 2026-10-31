# -*- coding: utf-8 -*-
"""策略广场：公开分享的回测快照（标题/正文 + 指标与曲线）。"""
from __future__ import annotations

import json
from typing import Any

from services.core.db import get_conn

_MAX_CURVE_POINTS = 360
_MAX_TITLE = 120
_MAX_BODY = 8000
_MAX_CODE = 200_000


def ensure_strategy_plaza_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_plaza_items (
              id              BIGSERIAL PRIMARY KEY,
              author_id       BIGINT NOT NULL REFERENCES users(id),
              title           TEXT NOT NULL,
              body            TEXT NOT NULL DEFAULT '',
              source_run_id   TEXT,
              snapshot        JSONB NOT NULL DEFAULT '{}'::jsonb,
              view_count      INTEGER NOT NULL DEFAULT 0,
              status          TEXT NOT NULL DEFAULT 'published',
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT strategy_plaza_status_chk
                CHECK (status IN ('published', 'hidden'))
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_strategy_plaza_created
            ON strategy_plaza_items (created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_strategy_plaza_status_created
            ON strategy_plaza_items (status, created_at DESC)
            """
        )


def _downsample_curve(points: Any, limit: int = _MAX_CURVE_POINTS) -> list[dict[str, Any]]:
    if not isinstance(points, list) or not points:
        return []
    cleaned: list[dict[str, Any]] = []
    for p in points:
        if not isinstance(p, dict):
            continue
        date = p.get("date")
        if date is None:
            continue
        row: dict[str, Any] = {"date": str(date)}
        if p.get("value") is not None:
            try:
                row["value"] = float(p["value"])
            except (TypeError, ValueError):
                continue
        if p.get("drawdown") is not None:
            try:
                row["drawdown"] = float(p["drawdown"])
            except (TypeError, ValueError):
                pass
        cleaned.append(row)
    n = len(cleaned)
    if n <= limit:
        return cleaned
    step = (n - 1) / (limit - 1)
    out: list[dict[str, Any]] = []
    for i in range(limit):
        idx = min(n - 1, int(round(i * step)))
        out.append(cleaned[idx])
    return out


def _slim_metrics(raw: Any) -> dict[str, float | None]:
    if not isinstance(raw, dict):
        return {}
    keys = (
        "annual_return",
        "total_return",
        "cumulative_return",
        "max_drawdown",
        "sharpe",
        "sortino",
        "calmar",
        "win_rate",
        "volatility",
        "annual_vol",
        "turnover",
        "avg_turnover",
        "alpha",
        "beta",
    )
    out: dict[str, float | None] = {}
    for k in keys:
        v = raw.get(k)
        if v is None:
            out[k] = None
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            out[k] = None
    return out


def build_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = _slim_metrics(payload.get("metrics"))
    excess = payload.get("excess_return")
    try:
        excess_f = float(excess) if excess is not None else None
    except (TypeError, ValueError):
        excess_f = None
    code = payload.get("strategy_code")
    code_s = str(code).strip() if code else ""
    if len(code_s) > _MAX_CODE:
        code_s = code_s[:_MAX_CODE]
    return {
        "metrics": metrics,
        "excess_return": excess_f,
        "equity_curve": _downsample_curve(payload.get("equity_curve")),
        "benchmark_curve": _downsample_curve(payload.get("benchmark_curve")),
        "date_range": payload.get("date_range")
        if isinstance(payload.get("date_range"), dict)
        else None,
        "universe": str(payload.get("universe") or "").strip() or None,
        "benchmark": str(payload.get("benchmark") or "").strip() or None,
        "universe_label": str(payload.get("universe_label") or "").strip() or None,
        "benchmark_label": str(payload.get("benchmark_label") or "").strip() or None,
        "strategy_code": code_s or None,
        "range_label": str(payload.get("range_label") or "").strip() or None,
        "engine_mode": (
            "event"
            if str(payload.get("engine_mode") or "").strip().lower() == "event"
            else "vectorized"
            if str(payload.get("engine_mode") or "").strip()
            else None
        ),
    }


def _row_to_item(row: Any, *, include_code: bool = True) -> dict[str, Any]:
    snap = row.get("snapshot") or {}
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except Exception:
            snap = {}
    if not isinstance(snap, dict):
        snap = {}
    if not include_code:
        snap = {**snap, "strategy_code": None}
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "body": row["body"] or "",
        "source_run_id": row.get("source_run_id"),
        "snapshot": snap,
        "view_count": int(row.get("view_count") or 0),
        "status": row.get("status") or "published",
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "author": {
            "id": int(row["author_id"]) if row.get("author_id") is not None else None,
            "username": row.get("username"),
            "display_name": row.get("display_name") or row.get("username"),
            "avatar_url": row.get("avatar_url"),
        },
    }


_SELECT = """
    SELECT p.*, u.username, u.display_name, u.avatar_url
    FROM strategy_plaza_items p
    JOIN users u ON u.id = p.author_id
"""


_SORT_SQL = {
    "newest": "p.created_at DESC",
    "oldest": "p.created_at ASC",
    "views": "p.view_count DESC NULLS LAST, p.created_at DESC",
    "annual": (
        "(NULLIF(p.snapshot->'metrics'->>'annual_return',''))::float "
        "DESC NULLS LAST, p.created_at DESC"
    ),
    "sharpe": (
        "(NULLIF(p.snapshot->'metrics'->>'sharpe',''))::float "
        "DESC NULLS LAST, p.created_at DESC"
    ),
    "mdd": (
        # 最大回撤通常为负：按绝对值更小（更接近 0）排前 → DESC on signed value
        "(NULLIF(p.snapshot->'metrics'->>'max_drawdown',''))::float "
        "DESC NULLS LAST, p.created_at DESC"
    ),
    "excess": (
        "(NULLIF(p.snapshot->>'excess_return',''))::float "
        "DESC NULLS LAST, p.created_at DESC"
    ),
}


def list_plaza_items(
    *,
    limit: int = 30,
    offset: int = 0,
    q: str | None = None,
    sort: str | None = None,
    universe: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    q = (q or "").strip()
    sort_key = (sort or "newest").strip().lower()
    if sort_key not in _SORT_SQL:
        sort_key = "newest"
    order_sql = _SORT_SQL[sort_key]
    uni = (universe or "").strip().upper()
    if uni in ("", "ALL", "*"):
        uni = ""

    where = ["p.status = 'published'"]
    params: list[Any] = []
    if q:
        where.append("(p.title ILIKE %s OR p.body ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    if uni:
        label_map = {
            "CSI300": "沪深300",
            "CSI500": "中证500",
            "CSI1000": "中证1000",
            "CSI800": "中证800",
            "SSE50": "上证50",
        }
        where.append(
            "(UPPER(COALESCE(p.snapshot->>'universe','')) = %s "
            "OR COALESCE(p.snapshot->>'universe_label','') = %s)"
        )
        params.extend([uni, label_map.get(uni, uni)])

    where_sql = " AND ".join(where)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            {_SELECT}
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT %s OFFSET %s
            """,
            (*params, limit, offset),
        ).fetchall()
        total = conn.execute(
            f"""
            SELECT COUNT(*)::int AS c
            FROM strategy_plaza_items p
            WHERE {where_sql}
            """,
            tuple(params),
        ).fetchone()["c"]
    items = [_row_to_item(r, include_code=False) for r in rows]
    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "sort": sort_key,
        "universe": uni or None,
    }


def get_plaza_item(item_id: int, *, bump_view: bool = True) -> dict[str, Any] | None:
    with get_conn() as conn:
        if bump_view:
            conn.execute(
                """
                UPDATE strategy_plaza_items
                SET view_count = view_count + 1
                WHERE id = %s AND status = 'published'
                """,
                (item_id,),
            )
        row = conn.execute(
            f"""
            {_SELECT}
            WHERE p.id = %s AND p.status = 'published'
            """,
            (item_id,),
        ).fetchone()
    if not row:
        return None
    return _row_to_item(row, include_code=True)


def create_plaza_item(
    author_id: int,
    *,
    title: str,
    body: str,
    snapshot: dict[str, Any],
    source_run_id: str | None = None,
) -> dict[str, Any]:
    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        raise ValueError("标题不能为空")
    if len(title) > _MAX_TITLE:
        title = title[:_MAX_TITLE]
    if len(body) > _MAX_BODY:
        body = body[:_MAX_BODY]
    snap = build_snapshot(snapshot if isinstance(snapshot, dict) else {})
    with get_conn() as conn:
        rid = (source_run_id or "").strip()
        if not rid:
            raise ValueError("发布必须绑定一次已验证的回测运行")
        run = conn.execute(
            "SELECT verified FROM strategy_runs WHERE user_id = %s AND id = %s",
            (author_id, rid),
        ).fetchone()
        if not run or not bool(run.get("verified")):
            raise PermissionError("源回测运行未通过服务端验证，不能发布")
        row = conn.execute(
            """
            INSERT INTO strategy_plaza_items
              (author_id, title, body, source_run_id, snapshot, status)
            VALUES (%s, %s, %s, %s, %s::jsonb, 'published')
            RETURNING id
            """,
            (
                author_id,
                title,
                body,
                (source_run_id or "").strip() or None,
                json.dumps(snap, ensure_ascii=False),
            ),
        ).fetchone()
        item_id = int(row["id"])
        full = conn.execute(
            f"""
            {_SELECT}
            WHERE p.id = %s
            """,
            (item_id,),
        ).fetchone()
    return _row_to_item(full, include_code=True)


def hide_plaza_item(item_id: int, author_id: int, *, as_admin: bool = False) -> bool:
    with get_conn() as conn:
        if as_admin:
            row = conn.execute(
                """
                UPDATE strategy_plaza_items
                SET status = 'hidden', updated_at = NOW()
                WHERE id = %s AND status = 'published'
                RETURNING id
                """,
                (item_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                UPDATE strategy_plaza_items
                SET status = 'hidden', updated_at = NOW()
                WHERE id = %s AND author_id = %s AND status = 'published'
                RETURNING id
                """,
                (item_id, author_id),
            ).fetchone()
    return bool(row)
