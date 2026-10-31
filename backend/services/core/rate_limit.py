# -*- coding: utf-8 -*-
"""进程内滑动窗口限流，用于登录/注册等公开端点的暴力破解与轰炸防护。

不引入外部依赖；阈值可通过环境变量调整（见 .env.example 的 AUTH_*_RATE_LIMIT）。
注意：仅适用于单 worker 部署（当前 api_server.py 即 workers=1）；
多 worker 部署时每个进程各自计数，实际放行量约为 配置值 × worker 数。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_BUCKETS: dict[str, deque[float]] = {}
_LOCK = threading.Lock()
_MAX_KEYS = 10000  # 防止恶意轮换 IP 撑爆内存；超上限时整体重置（宁可短暂放过限流）


def _client_key(request: Request) -> str:
    xf = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xf:
        return xf.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def enforce_rate_limit_key(key: str, *, scope: str, limit: int, window_sec: int) -> None:
    """同一 key 在 window_sec 秒内最多调用 limit 次，超出抛 429。"""
    key = f"{scope}:{key}"
    now = time.monotonic()
    with _LOCK:
        if len(_BUCKETS) >= _MAX_KEYS:
            _BUCKETS.clear()
        bucket = _BUCKETS.setdefault(key, deque())
        while bucket and now - bucket[0] > window_sec:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后再试",
                headers={"Retry-After": str(max(1, int(window_sec)))},
            )
        bucket.append(now)
        if not bucket:  # 理论不可达；防御空桶滞留
            _BUCKETS.pop(key, None)


def enforce_rate_limit(request: Request, *, scope: str, limit: int, window_sec: int) -> None:
    """同一 IP 在 window_sec 秒内最多调用 limit 次，超出抛 429。"""
    enforce_rate_limit_key(_client_key(request), scope=scope, limit=limit, window_sec=window_sec)
