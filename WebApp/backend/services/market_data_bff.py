# -*- coding: utf-8 -*-
"""行情只读 BFF：本机直连 RE，避免浏览器/vite 经 Clash 把 /yg-api 卡死。

进程内短缓存：同一标的/区间几分钟内复用，避免「离开再进」冷打 RE。
"""
from __future__ import annotations

import os
import threading
import time
import urllib.parse
from typing import Any

from services.lan_http import get_json

RE_BASE = os.environ.get("YG_RE_BASE", "http://192.168.3.64:9527").rstrip("/")
_CACHE_TTL_SEC = float(os.environ.get("MARKET_DAILY_CACHE_TTL", "600"))
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _cache_key(symbol: str, start: str | None, end: str | None) -> str:
    return f"{symbol}|{start or ''}|{end or ''}"


def fetch_market_daily(
    symbol: str,
    *,
    start: str | None = None,
    end: str | None = None,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    code = (symbol or "").strip()
    if not code:
        raise ValueError("缺少股票代码")
    key = _cache_key(code, start, end)
    now = time.monotonic()
    if not bypass_cache and _CACHE_TTL_SEC > 0:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and now - hit[0] < _CACHE_TTL_SEC:
                return hit[1]
    q: dict[str, str] = {}
    if start:
        q["start"] = start
    if end:
        q["end"] = end
    qs = urllib.parse.urlencode(q)
    path = f"/api/market-data/daily/{urllib.parse.quote(code)}"
    url = f"{RE_BASE}{path}" + (f"?{qs}" if qs else "")
    data = get_json(url, timeout=20)
    if not isinstance(data, dict):
        raise RuntimeError("RE 日线返回非 JSON 对象")
    if _CACHE_TTL_SEC > 0:
        with _cache_lock:
            _cache[key] = (time.monotonic(), data)
            # 简单防膨胀
            if len(_cache) > 64:
                oldest = sorted(_cache.items(), key=lambda kv: kv[1][0])[:16]
                for k, _ in oldest:
                    _cache.pop(k, None)
    return data
