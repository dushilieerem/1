# -*- coding: utf-8 -*-
"""RE 策略能力清单（/api/strategy-capabilities）的拉取与缓存。

预检以 RE 的清单为准，避免本地白名单漂移导致「预检通过但回测报 unsupported_api」。
拉取失败时返回 None，调用方回退到本地清单。
"""
from __future__ import annotations

import threading
import time
from typing import Any

from services.core.re_http_gateway import forward_re

CACHE_TTL_SEC = 600.0

_lock = threading.Lock()
_cached: dict[str, Any] | None = None
_cached_at = 0.0


def _fetch() -> dict[str, Any] | None:
    try:
        status, _headers, data = forward_re("GET", "/api/strategy-capabilities", timeout=5)
    except Exception:  # noqa: BLE001 - RE 不可用时静默回退
        return None
    if status != 200 or not isinstance(data, dict):
        return None
    return data


def capabilities(*, force: bool = False) -> dict[str, Any] | None:
    """返回能力清单；TTL 内复用缓存，失败返回 None（不缓存失败）。"""
    global _cached, _cached_at
    now = time.monotonic()
    with _lock:
        if not force and _cached is not None and now - _cached_at < CACHE_TTL_SEC:
            return _cached
    data = _fetch()
    if data is None:
        return None
    with _lock:
        _cached = data
        _cached_at = now
    return data


def joinquant_capabilities() -> dict[str, Any] | None:
    data = capabilities()
    if not data:
        return None
    dialects = data.get("dialects") or {}
    item = dialects.get("joinquant")
    return item if isinstance(item, dict) else None


def unsupported_map() -> dict[str, str] | None:
    """{api: reason}；清单不可用时返回 None。"""
    item = joinquant_capabilities()
    if not item:
        return None
    out: dict[str, str] = {}
    for row in item.get("unsupported_apis") or []:
        if isinstance(row, dict) and row.get("api"):
            out[str(row["api"])] = str(row.get("reason") or "")
        elif isinstance(row, str):
            out[row] = ""
    return out


def version() -> str | None:
    data = capabilities()
    return str(data.get("version")) if data and data.get("version") else None


def reset_cache() -> None:
    global _cached, _cached_at
    with _lock:
        _cached = None
        _cached_at = 0.0


__all__ = ["capabilities", "joinquant_capabilities", "reset_cache", "unsupported_map", "version"]
