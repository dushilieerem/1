# -*- coding: utf-8 -*-
"""浏览器 → 本机 /api → ResearchEngine（薄转发，无自建队列）。"""
from __future__ import annotations

import time
from threading import Lock
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.deps import optional_user, require_user
from services.core.backtest_params import validate_execution_timing
from services.core.db import get_conn
from services.core.env_config import env
from services.core.re_http_gateway import forward_re, rewrite_run_poll_url
from services.research import asset_store
from services.strategy.result_signature import sign_result

router = APIRouter(tags=["re-gateway"])


def _float_env(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


_MARKET_CACHE_TTL = _float_env("SVQUANT_MARKET_CACHE_TTL_SEC", 300.0)
_MARKET_CACHE_STALE_TTL = _float_env("SVQUANT_MARKET_CACHE_STALE_TTL_SEC", 3600.0)
_MARKET_FETCH_TIMEOUT = _float_env("SVQUANT_MARKET_RE_TIMEOUT_SEC", 5.0)
_RE_HEALTH_TIMEOUT = _float_env("SVQUANT_RE_HEALTH_TIMEOUT_SEC", 2.0)
_RE_HEALTH_CACHE_TTL = _float_env("SVQUANT_RE_HEALTH_CACHE_TTL_SEC", 5.0)
_CACHE_LOCK = Lock()
_CACHE: dict[str, dict[str, Any]] = {}


def _resp(status: int, headers: dict[str, str], data: Any) -> JSONResponse:
    return JSONResponse(
        content=data if data is not None else {},
        status_code=status,
        headers=headers,
    )


def _cache_headers(headers: dict[str, str], *, state: str) -> dict[str, str]:
    out = dict(headers)
    out["X-SVQuant-Cache"] = state
    if state in {"hit", "stale"}:
        out["Cache-Control"] = f"public, max-age={int(_MARKET_CACHE_TTL)}"
    return out


def _cached_re_get(cache_key: str, path: str) -> tuple[int, dict[str, str], Any]:
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    cached_ttl = _MARKET_CACHE_STALE_TTL if isinstance(cached, dict) and bool((cached.get("data") or {}).get("_fallback")) else _MARKET_CACHE_TTL
    if cached and now - float(cached["at"]) <= cached_ttl:
        return int(cached["status"]), _cache_headers(cached["headers"], state="hit"), cached["data"]

    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        cached_ttl = _MARKET_CACHE_STALE_TTL if isinstance(cached, dict) and bool((cached.get("data") or {}).get("_fallback")) else _MARKET_CACHE_TTL
        if cached and now - float(cached["at"]) <= cached_ttl:
            return int(cached["status"]), _cache_headers(cached["headers"], state="hit"), cached["data"]

        status, headers, data = forward_re("GET", path, timeout=_MARKET_FETCH_TIMEOUT)
        if 200 <= status < 300:
            _CACHE[cache_key] = {
                "at": time.monotonic(),
                "status": status,
                "headers": headers,
                "data": data,
            }
            return status, _cache_headers(headers, state="miss"), data

        cached = _CACHE.get(cache_key)
        if cached and now - float(cached["at"]) <= _MARKET_CACHE_STALE_TTL:
            stale_data = cached["data"]
            if isinstance(stale_data, dict):
                stale_data = {**stale_data, "_stale": True, "_upstream_status": status}
            return int(cached["status"]), _cache_headers(cached["headers"], state="stale"), stale_data
        return status, _cache_headers(headers, state="error"), data


def _re_health_with_fallback() -> tuple[int, dict[str, str], Any]:
    now = time.monotonic()
    cached = _CACHE.get("re_health")
    if cached and now - float(cached["at"]) <= _RE_HEALTH_CACHE_TTL:
        return int(cached["status"]), dict(cached["headers"]), cached["data"]
    status, headers, data = forward_re("GET", "/api/health", timeout=_RE_HEALTH_TIMEOUT)
    if 200 <= status < 300:
        _CACHE["re_health"] = {
            "at": time.monotonic(),
            "status": status,
            "headers": headers,
            "data": data,
        }
        return status, headers, data
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM re_factor_catalog_snapshot").fetchone()
            count = int(row["n"] if row else 0)
    except Exception:
        count = 0
    if count > 0:
        headers = {"X-SVQuant-RE-Health": "degraded-local-snapshot"}
        data = {
            "ok": True,
            "status": "degraded",
            "health_endpoint_status": status,
            "local_catalog_snapshot": True,
            "catalog_count": count,
        }
        _CACHE["re_health"] = {
            "at": time.monotonic(),
            "status": 200,
            "headers": headers,
            "data": data,
        }
        return 200, headers, data
    return status, headers, data


# —— 策略回测（对方若已异步则 202+轮询；否则同步长等）——


@router.post("/api/backtest/strategy")
def backtest_strategy_submit(
    body: dict[str, Any],
    _user: dict = Depends(require_user),
) -> JSONResponse:
    payload = body if isinstance(body, dict) else {}
    try:
        validate_execution_timing(payload)
        payload = asset_store.apply_asset_refs(int(_user["id"]), payload)
    except KeyError:
        return _resp(404, {}, {"error": "研究资产不存在"})
    except ValueError as exc:
        return _resp(400, {}, {"error": str(exc)})
    status, headers, data = forward_re(
        "POST",
        "/api/backtest/strategy",
        payload=payload,
        timeout=1800,
    )
    data = rewrite_run_poll_url(data, "/api/backtest/strategy")
    if status == 202 or (isinstance(data, dict) and data.get("run_id")):
        # P0-02：当前 RE 只有同步策略回测；不暴露会 404 的轮询路由。
        return _resp(502, headers, {"error": "ResearchEngine 当前仅支持同步策略回测"})
    if 200 <= status < 300 and isinstance(data, dict) and not data.get("error"):
        data = {**data, "_svquant_verified_token": sign_result(int(_user["id"]), data)}
    return _resp(status, headers, data)


# —— 计算服务健康（避免与本机 /api/health 冲突）——


@router.get("/api/re/health")
def re_health(_user: dict | None = Depends(optional_user)) -> JSONResponse:
    status, headers, data = _re_health_with_fallback()
    return _resp(status, headers, data)


# —— 行情只读列表（日线已有本机 BFF）——


# —— 行情只读列表（日线已有本机 BFF）——


@router.get("/api/market-data/symbols")
def market_symbols() -> JSONResponse:
    status, headers, data = _cached_re_get("market_symbols", "/api/market-data/symbols")
    return _resp(status, headers, data)


@router.get("/api/market-data/indices")
def market_indices() -> JSONResponse:
    status, headers, data = _cached_re_get("market_indices", "/api/market-data/indices")
    return _resp(status, headers, data)


@router.get("/api/market-data/indices/{key}/constituents")
def market_index_constituents(key: str, request: Request) -> JSONResponse:
    # 透传查询串（若有）
    q = dict(request.query_params) if request.query_params else None
    status, headers, data = forward_re(
        "GET",
        f"/api/market-data/indices/{key}/constituents",
        query=q,
        timeout=60,
    )
    return _resp(status, headers, data)
