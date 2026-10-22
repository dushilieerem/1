# -*- coding: utf-8 -*-
"""ResearchEngine 模拟盘内部接口客户端。"""
from __future__ import annotations

from typing import Any

from services.core.re_http_gateway import forward_re


class PaperTradingReError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        http_status: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail


def _detail_code(data: Any) -> tuple[str, str]:
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, dict):
            return str(detail.get("code") or ""), str(detail.get("message") or "")
        if isinstance(detail, str) and detail:
            return "", detail
        if isinstance(data.get("error"), str):
            return "", str(data["error"])
    return "", ""


def _raise(status: int, data: Any) -> None:
    code, message = _detail_code(data)
    if status == 504:
        raise PaperTradingReError(
            code="RE_TIMEOUT", message=message or "ResearchEngine 结算超时", http_status=504
        )
    if status in (502, 503):
        raise PaperTradingReError(
            code=code or "RE_UNAVAILABLE",
            message=message or "ResearchEngine 不可用",
            http_status=status,
            detail=data,
        )
    if status == 429:
        raise PaperTradingReError(
            code=code or "RE_BUSY",
            message=message or "ResearchEngine 结算繁忙",
            http_status=429,
            detail=data,
        )
    raise PaperTradingReError(
        code=code or f"HTTP_{status}",
        message=message or f"ResearchEngine 返回 HTTP {status}",
        http_status=status,
        detail=data,
    )


def fetch_status(
    settlement_date: str | None = None, *, timeout: float = 15
) -> dict[str, Any]:
    query = {"date": settlement_date} if settlement_date else None
    status, _headers, data = forward_re(
        "GET", "/api/internal/paper-trading/status", query=query, timeout=timeout
    )
    if status != 200:
        _raise(status, data)
    return data if isinstance(data, dict) else {}


def fetch_trading_days(
    start: str | None = None, end: str | None = None, *, timeout: float = 30
) -> dict[str, Any]:
    query = {key: value for key, value in (("start", start), ("end", end)) if value}
    status, _headers, data = forward_re(
        "GET",
        "/api/internal/paper-trading/trading-days",
        query=query or None,
        timeout=timeout,
    )
    if status != 200:
        _raise(status, data)
    return data if isinstance(data, dict) else {}


def settle(payload: dict[str, Any], *, timeout: float = 300) -> dict[str, Any]:
    status, _headers, data = forward_re(
        "POST", "/api/internal/paper-trading/settle", payload=payload, timeout=timeout
    )
    if status != 200:
        _raise(status, data)
    return data if isinstance(data, dict) else {}


__all__ = [
    "PaperTradingReError",
    "fetch_status",
    "fetch_trading_days",
    "settle",
]
