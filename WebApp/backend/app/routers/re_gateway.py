# -*- coding: utf-8 -*-
"""浏览器 → 本机 /api → ResearchEngine（薄转发，无自建队列）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.deps import optional_user, require_user
from services.core.re_http_gateway import forward_re, rewrite_run_poll_url

router = APIRouter(tags=["re-gateway"])


def _resp(status: int, headers: dict[str, str], data: Any) -> JSONResponse:
    return JSONResponse(
        content=data if data is not None else {},
        status_code=status,
        headers=headers,
    )


# —— 策略回测（对方若已异步则 202+轮询；否则同步长等）——


@router.post("/api/backtest/strategy")
def backtest_strategy_submit(
    body: dict[str, Any],
    _user: dict = Depends(require_user),
) -> JSONResponse:
    status, headers, data = forward_re(
        "POST",
        "/api/backtest/strategy",
        payload=body if isinstance(body, dict) else {},
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
    status, headers, data = forward_re("GET", "/api/health", timeout=15)
    return _resp(status, headers, data)


# —— AI（对方侧；本机不存 Key）——


@router.post("/api/ai/factor-generations")
def ai_factor_generations(
    body: dict[str, Any], _user: dict = Depends(require_user)
) -> JSONResponse:
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
    status, headers, data = forward_re("GET", "/api/market-data/symbols", timeout=60)
    return _resp(status, headers, data)


@router.get("/api/market-data/indices")
def market_indices() -> JSONResponse:
    status, headers, data = forward_re("GET", "/api/market-data/indices", timeout=60)
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
