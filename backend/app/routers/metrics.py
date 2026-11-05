# -*- coding: utf-8 -*-
"""Prometheus 指标：库表聚合计数 + 进程内 HTTP 指标。

只暴露聚合计数，不含用户名/内容；默认仅本机可读，生产采集端配置 METRICS_TOKEN。
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from services.core import http_metrics
from services.core.db import get_conn
from services.core.env_config import env

router = APIRouter(tags=["metrics"])


def _authorized(request: Request) -> bool:
    token = (env("METRICS_TOKEN", "") or "").strip()
    if token:
        provided = request.headers.get("x-metrics-token") or ""
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            provided = auth.split(None, 1)[1].strip()
        return hmac.compare_digest(provided, token)
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1"}


def _count(conn, table: str, where: str = "") -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} {where}").fetchone()
        return int(row["n"] or 0)
    except Exception:
        return 0


@router.get("/api/metrics")
def metrics(request: Request) -> Response:
    if not _authorized(request):
        raise HTTPException(status_code=403, detail="metrics 需要 METRICS_TOKEN 或本机访问")
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
    lines.append(http_metrics.render().rstrip("\n"))
    return Response(
        content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8"
    )
