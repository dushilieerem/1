# -*- coding: utf-8 -*-
"""最小 Prometheus 指标（P1-O03 首版）。

只暴露聚合计数，不含用户名/内容；建议仅内网抓取。
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from services.core.db import get_conn

router = APIRouter(tags=["metrics"])


def _count(conn, table: str, where: str = "") -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} {where}").fetchone()
        return int(row["n"] or 0)
    except Exception:
        return 0


@router.get("/api/metrics")
def metrics() -> Response:
    lines = ["# HELP svquant_up SVQuant API up", "# TYPE svquant_up gauge", "svquant_up 1"]
    try:
        with get_conn() as conn:
            for table, name in (
                ("users", "svquant_users"),
                ("posts", "svquant_posts"),
                ("news_items", "svquant_news_items"),
                ("strategy_runs", "svquant_strategy_runs"),
                ("ai_usage", "svquant_ai_usage_rows"),
                ("app_audit_logs", "svquant_audit_rows"),
            ):
                lines += [f"# TYPE {name} gauge", f"{name} {_count(conn, table)}"]
            open_reports = _count(conn, "community_reports", "WHERE status='open'")
            lines += [
                "# TYPE svquant_open_community_reports gauge",
                f"svquant_open_community_reports {open_reports}",
            ]
    except Exception:
        lines += ["# TYPE svquant_db_up gauge", "svquant_db_up 0"]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
