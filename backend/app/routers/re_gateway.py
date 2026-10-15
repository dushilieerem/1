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
from services.core.ai_factor_input import factor_prompt_error
from services.core.db import get_conn
from services.core.env_config import env
from services.core.re_http_gateway import forward_re, rewrite_run_poll_url

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

_DEFAULT_SYMBOLS = [
    ("000001.SZ", "平安银行"),
    ("000002.SZ", "万科A"),
    ("000858.SZ", "五粮液"),
    ("002415.SZ", "海康威视"),
    ("002594.SZ", "比亚迪"),
    ("300750.SZ", "宁德时代"),
    ("600000.SH", "浦发银行"),
    ("600036.SH", "招商银行"),
    ("600519.SH", "贵州茅台"),
    ("600887.SH", "伊利股份"),
    ("601318.SH", "中国平安"),
    ("601398.SH", "工商银行"),
]

_DEFAULT_INDICES = [
    {"code": "CSI300", "name": "沪深300"},
    {"code": "CSI500", "name": "中证500"},
    {"code": "CSI1000", "name": "中证1000"},
    {"code": "SSE50", "name": "上证50"},
    {"code": "SZSE100", "name": "深证100"},
]


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
        fallback = _local_market_fallback(cache_key, status)
        if fallback is not None:
            _CACHE[cache_key] = {
                "at": time.monotonic(),
                "status": 200,
                "headers": headers,
                "data": fallback,
            }
            return 200, _cache_headers(headers, state="fallback"), fallback
        return status, _cache_headers(headers, state="error"), data


def _local_market_fallback(cache_key: str, upstream_status: int) -> dict[str, Any] | None:
    if cache_key == "market_indices":
        return {"ok": True, "indices": _DEFAULT_INDICES, "_fallback": True, "_upstream_status": upstream_status}
    if cache_key != "market_symbols":
        return None

    seen: set[str] = set()
    symbols: list[dict[str, str]] = []

    def add(symbol: Any, name: Any = "") -> None:
        code = str(symbol or "").strip().upper()
        if not code or code in seen:
            return
        seen.add(code)
        symbols.append({"symbol": code, "name": str(name or "").strip()})

    for code, name in _DEFAULT_SYMBOLS:
        add(code, name)

    try:
        with get_conn() as conn:
            try:
                for row in conn.execute(
                    """
                    SELECT symbol, max(name) AS name
                    FROM user_watchlist_symbols
                    WHERE symbol IS NOT NULL AND symbol <> ''
                    GROUP BY symbol
                    ORDER BY symbol
                    LIMIT 200
                    """
                ).fetchall():
                    add(row.get("symbol"), row.get("name"))
            except Exception:
                conn.rollback()
            try:
                for row in conn.execute(
                    """
                    SELECT DISTINCT jsonb_array_elements_text(symbols) AS symbol
                    FROM news_items
                    WHERE jsonb_typeof(symbols) = 'array'
                    LIMIT 200
                    """
                ).fetchall():
                    add(row.get("symbol"))
            except Exception:
                conn.rollback()
    except Exception:
        pass

    return {
        "ok": True,
        "symbols": symbols,
        "unmapped_count": 0,
        "_fallback": True,
        "_upstream_status": upstream_status,
    }


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
    except ValueError as exc:
        return _resp(400, {}, {"error": str(exc)})
    status, headers, data = forward_re(
        "POST",
        "/api/backtest/strategy",
        payload=payload,
        timeout=1800,
    )
    data = rewrite_run_poll_url(data, "/api/backtest/strategy")
    if isinstance(data, dict) and data.get("run_id"):
        headers = {
            **headers,
            "Location": f"/api/backtest/strategy/{data['run_id']}",
        }
    return _resp(status, headers, data)


@router.get("/api/backtest/strategy/{run_id}")
def backtest_strategy_poll(
    run_id: str, _user: dict = Depends(require_user)
) -> JSONResponse:
    status, headers, data = forward_re(
        "GET", f"/api/backtest/strategy/{run_id}", timeout=60
    )
    return _resp(status, headers, data)


@router.delete("/api/backtest/strategy/{run_id}")
def backtest_strategy_cancel(
    run_id: str, _user: dict = Depends(require_user)
) -> JSONResponse:
    status, headers, data = forward_re(
        "DELETE", f"/api/backtest/strategy/{run_id}", timeout=60
    )
    return _resp(status, headers, data)


# —— 计算服务健康（避免与本机 /api/health 冲突）——


@router.get("/api/re/health")
def re_health(_user: dict | None = Depends(optional_user)) -> JSONResponse:
    status, headers, data = _re_health_with_fallback()
    return _resp(status, headers, data)


# —— AI（对方侧；本机不存 Key）——


@router.post("/api/ai/factor-generations")
def ai_factor_generations(
    body: dict[str, Any], _user: dict = Depends(require_user)
) -> JSONResponse:
    error = factor_prompt_error(body.get("prompt"))
    if error:
        return JSONResponse(status_code=422, content={"detail": error})
    status, headers, data = forward_re(
        "POST",
        "/api/ai/factor-generations",
        payload=body if isinstance(body, dict) else {},
        timeout=600,
    )
    return _resp(status, headers, data)


@router.post("/api/ai/strategy-generations")
def ai_strategy_generations(
    body: dict[str, Any], _user: dict = Depends(require_user)
) -> JSONResponse:
    status, headers, data = forward_re(
        "POST",
        "/api/ai/strategy-generations",
        payload=body if isinstance(body, dict) else {},
        timeout=600,
    )
    return _resp(status, headers, data)


@router.post("/api/ai/backtest-interpretations")
def ai_backtest_interpretations(
    body: dict[str, Any], _user: dict = Depends(require_user)
) -> JSONResponse:
    status, headers, data = forward_re(
        "POST",
        "/api/ai/backtest-interpretations",
        payload=body if isinstance(body, dict) else {},
        timeout=600,
    )
    return _resp(status, headers, data)


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
