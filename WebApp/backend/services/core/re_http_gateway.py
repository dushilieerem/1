# -*- coding: utf-8 -*-
"""ResearchEngine 薄网关：本机转发，不自建队列；浏览器只打 /api。"""
from __future__ import annotations

import os
import urllib.parse
from typing import Any

from services.core.lan_http import request_json

RE_BASE = os.environ.get("YG_RE_BASE", "http://192.168.3.64:9527").rstrip("/")


def forward_re(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
    timeout: float | int = 120,
) -> tuple[int, dict[str, str], Any]:
    """转发到 RE；path 须以 / 开头（如 /api/backtest/strategy）。"""
    p = path if path.startswith("/") else f"/{path}"
    url = f"{RE_BASE}{p}"
    if query:
        qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        if qs:
            url = f"{url}?{qs}"
    status, headers, data = request_json(
        url, method=method.upper(), payload=payload, timeout=timeout
    )
    out: dict[str, str] = {}
    ra = headers.get("retry-after")
    if ra:
        out["Retry-After"] = ra
    return status, out, data


def rewrite_run_poll_url(data: Any, base_path: str) -> Any:
    """把对方 poll_url 改写为本站路径。"""
    if not isinstance(data, dict):
        return data
    run_id = str(data.get("run_id") or "").strip()
    if not run_id:
        return data
    base = base_path.rstrip("/")
    data = {**data, "poll_url": f"{base}/{run_id}"}
    return data
