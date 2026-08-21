# -*- coding: utf-8 -*-
"""因子回测异步薄 BFF（方案 A）：本机原样转发对方提交 / 轮询 / 取消，不自建队列。"""
from __future__ import annotations

import os
from typing import Any

from services.core.lan_http import request_json

RE_BASE = os.environ.get("YG_RE_BASE", "http://192.168.3.64:9527").rstrip("/")
RE_FACTOR_BT = f"{RE_BASE}/api/backtest/factor"

_SV_ONLY_KEYS = (
    "_svquant_ui",
    "_svquantDraftFactor",
    "_svquantDraftFactors",
)


def _strip_sv(payload: dict[str, Any] | None) -> dict[str, Any]:
    body = {k: v for k, v in (payload or {}).items() if k not in _SV_ONLY_KEYS}
    fc = body.get("factor_code")
    if fc is None or (isinstance(fc, str) and not fc.strip()):
        body.pop("factor_code", None)
    if body.get("library_name") is None:
        body.pop("library_name", None)
    return body


def _rewrite_poll(data: Any) -> Any:
    """把对方 poll_url 改写为本站路径，浏览器只认 /api。"""
    if not isinstance(data, dict):
        return data
    run_id = str(data.get("run_id") or "").strip()
    if run_id:
        data = {**data, "poll_url": f"/api/backtest/factor/{run_id}"}
    return data


def proxy_submit_factor_backtest(
    payload: dict[str, Any],
) -> tuple[int, dict[str, str], Any]:
    status, headers, data = request_json(
        RE_FACTOR_BT,
        method="POST",
        payload=_strip_sv(payload),
        timeout=120,
    )
    data = _rewrite_poll(data)
    out_headers: dict[str, str] = {}
    if isinstance(data, dict) and data.get("run_id"):
        out_headers["Location"] = f"/api/backtest/factor/{data['run_id']}"
    ra = headers.get("retry-after")
    if ra:
        out_headers["Retry-After"] = ra
    return status, out_headers, data


def proxy_get_factor_run(run_id: str) -> tuple[int, dict[str, str], Any]:
    rid = str(run_id or "").strip()
    if not rid:
        return 404, {}, {"error": "缺少 run_id"}
    status, headers, data = request_json(
        f"{RE_FACTOR_BT}/{rid}",
        method="GET",
        timeout=60,
    )
    out_headers: dict[str, str] = {}
    ra = headers.get("retry-after")
    if ra:
        out_headers["Retry-After"] = ra
    return status, out_headers, data


def proxy_cancel_factor_run(run_id: str) -> tuple[int, dict[str, str], Any]:
    rid = str(run_id or "").strip()
    if not rid:
        return 404, {}, {"error": "缺少 run_id"}
    return request_json(
        f"{RE_FACTOR_BT}/{rid}",
        method="DELETE",
        timeout=60,
    )
