# -*- coding: utf-8 -*-
"""因子评价记录（P1-F08）：评价建议落库 + 人工确认闭环 + 审计。

状态：
  suggested  评价 Agent 给出建议，尚未人工处理
  admitted   人工确认入库（可选同步写入用户自定义因子库）
  rejected   人工确认不入库
"""
from __future__ import annotations

import json
from typing import Any

from services.core.db import get_conn


def ensure_eval_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factor_eval_records (
              id           BIGSERIAL PRIMARY KEY,
              eval_id      TEXT NOT NULL UNIQUE,
              user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              report_id    TEXT,
              verdict      TEXT NOT NULL,
              status       TEXT NOT NULL DEFAULT 'suggested',
              note         TEXT,
              reasons      JSONB,
              metrics      JSONB,
              report       JSONB,
              factor_name  TEXT,
              factor_code  TEXT,
              decided_by   BIGINT,
              decided_at   TIMESTAMPTZ,
              created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_factor_eval_records_user "
            "ON factor_eval_records (user_id, created_at DESC)"
        )


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    for key in ("decided_at", "created_at"):
        value = item.get(key)
        if value is not None:
            item[key] = value.isoformat()
    item["admit"] = item.get("status") == "admitted"
    return item


def record_eval(
    *,
    user_id: int,
    out: dict[str, Any],
    report: dict[str, Any] | None,
) -> dict[str, Any]:
    """保存一次评价结果；eval_id 由评价 Agent 生成。"""
    ensure_eval_schema()
    report = report if isinstance(report, dict) else {}
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    request = report.get("request") if isinstance(report.get("request"), dict) else {}
    factor_name = str(request.get("factor_name") or "") or None
    factor_code = str(request.get("factor_code") or "") or None
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO factor_eval_records (
              eval_id, user_id, report_id, verdict, note, reasons, metrics,
              report, factor_name, factor_code
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (eval_id) DO NOTHING
            RETURNING id, created_at
            """,
            (
                str(out.get("eval_id") or ""),
                int(user_id),
                str(report.get("report_id") or "") or None,
                str(out.get("verdict") or "reject"),
                str(out.get("note") or ""),
                json.dumps(out.get("reasons") or [], ensure_ascii=False),
                json.dumps(metrics, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
                factor_name,
                factor_code,
            ),
        ).fetchone()
    if row is None:
        # 重复 eval_id：返回已有记录
        existing = get_eval(user_id, str(out.get("eval_id") or ""))
        if existing:
            return existing
        raise RuntimeError("评价记录写入失败")
    return {
        "id": int(row["id"]),
        "eval_id": str(out.get("eval_id") or ""),
        "created_at": row["created_at"].isoformat(),
        "status": "suggested",
    }


def list_evals(user_id: int, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    ensure_eval_schema()
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM factor_eval_records WHERE user_id = %s",
            (int(user_id),),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT id, eval_id, report_id, verdict, status, note, reasons,
                   factor_name, decided_by, decided_at, created_at
            FROM factor_eval_records
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (int(user_id), limit, offset),
        ).fetchall()
    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": int(total["n"] or 0),
        "limit": limit,
        "offset": offset,
    }


def get_eval(user_id: int, eval_id: str) -> dict[str, Any] | None:
    ensure_eval_schema()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, eval_id, user_id, report_id, verdict, status, note, reasons,
                   metrics, report, factor_name, factor_code, decided_by, decided_at,
                   created_at
            FROM factor_eval_records
            WHERE eval_id = %s AND user_id = %s
            """,
            (str(eval_id), int(user_id)),
        ).fetchone()
    return _row_to_dict(row) if row else None


def decide_eval(
    *,
    user_id: int,
    eval_id: str,
    admit: bool,
    note: str | None = None,
) -> dict[str, Any] | None:
    """人工确认：标记 admitted / rejected（只改评价记录，入库由路由负责）。"""
    ensure_eval_schema()
    status = "admitted" if admit else "rejected"
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE factor_eval_records
            SET status = %s,
                note = COALESCE(%s, note),
                decided_by = %s,
                decided_at = NOW()
            WHERE eval_id = %s AND user_id = %s
            RETURNING id, eval_id, report_id, verdict, status, note, reasons,
                      factor_name, decided_by, decided_at, created_at
            """,
            (status, note, int(user_id), str(eval_id), int(user_id)),
        ).fetchone()
    return _row_to_dict(row) if row else None
