# -*- coding: utf-8 -*-
"""轻量 HTTP 指标：进程内计数，暴露 Prometheus 文本，不引入额外依赖。

单 worker 部署下即可用；多副本时每个实例各自暴露，由采集端按 instance 聚合。
"""
from __future__ import annotations

import threading
import time
from collections import Counter

_LOCK = threading.Lock()
_REQUESTS: Counter[tuple[str, str, int]] = Counter()
_DURATION_SUM: Counter[tuple[str, str]] = Counter()
_DURATION_COUNT: Counter[tuple[str, str]] = Counter()
_BUCKET_COUNTS: Counter[tuple[str, str, float]] = Counter()
_IN_FLIGHT = 0
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def in_flight(delta: int) -> None:
    global _IN_FLIGHT
    with _LOCK:
        _IN_FLIGHT = max(0, _IN_FLIGHT + delta)


def observe(*, method: str, route: str, status: int, seconds: float) -> None:
    key = ((method or "UNKNOWN").upper(), route or "unmatched")
    with _LOCK:
        _REQUESTS[(key[0], key[1], int(status))] += 1
        _DURATION_SUM[key] += seconds
        _DURATION_COUNT[key] += 1
        for bucket in BUCKETS:
            if seconds <= bucket:
                _BUCKET_COUNTS[(key[0], key[1], bucket)] += 1


def render(*, pool: dict[str, int] | None = None) -> str:
    with _LOCK:
        requests = list(_REQUESTS.items())
        sums = list(_DURATION_SUM.items())
        counts = list(_DURATION_COUNT.items())
        buckets = list(_BUCKET_COUNTS.items())
        inflight = _IN_FLIGHT
    lines = [
        "# HELP svquant_http_in_flight 当前处理中的 HTTP 请求数",
        "# TYPE svquant_http_in_flight gauge",
        f"svquant_http_in_flight {inflight}",
        "# HELP svquant_http_requests_total HTTP 请求数（按路由模板/方法/状态）",
        "# TYPE svquant_http_requests_total counter",
    ]
    for (method, route, status), value in sorted(requests):
        lines.append(
            f'svquant_http_requests_total{{method="{_esc(method)}",route="{_esc(route)}",status="{status}"}} {value}'
        )
    lines += [
        "# HELP svquant_http_request_duration_seconds HTTP 请求耗时（秒）",
        "# TYPE svquant_http_request_duration_seconds histogram",
    ]
    for (method, route, bucket), value in sorted(buckets):
        lines.append(
            f'svquant_http_request_duration_seconds_bucket{{method="{_esc(method)}",route="{_esc(route)}",le="{bucket:g}"}} {value}'
        )
    # 每个 (method,route) 的 +Inf 桶等于总请求数
    totals = {(method, route): n for (method, route), n in dict(counts).items()}
    for (method, route), n in sorted(totals.items()):
        lines.append(
            f'svquant_http_request_duration_seconds_bucket{{method="{_esc(method)}",route="{_esc(route)}",le="+Inf"}} {n}'
        )
    for (method, route), value in sorted(dict(sums).items()):
        lines.append(
            f'svquant_http_request_duration_seconds_sum{{method="{_esc(method)}",route="{_esc(route)}"}} {value:.6f}'
        )
        lines.append(
            f'svquant_http_request_duration_seconds_count{{method="{_esc(method)}",route="{_esc(route)}"}} {totals.get((method, route), 0)}'
        )
    if pool is not None:
        lines += [
            "# HELP svquant_db_pool_connections 当前连接槽位数",
            "# TYPE svquant_db_pool_connections gauge",
            f'svquant_db_pool_connections{{state="used"}} {pool.get("used", 0)}',
            f'svquant_db_pool_connections{{state="idle"}} {pool.get("idle", 0)}',
            f'svquant_db_pool_connections{{state="limit"}} {pool.get("limit", 0)}',
        ]
    return "\n".join(lines) + "\n"


def reset() -> None:
    """测试用：清空进程内指标。"""
    global _IN_FLIGHT
    with _LOCK:
        _REQUESTS.clear()
        _DURATION_SUM.clear()
        _DURATION_COUNT.clear()
        _BUCKET_COUNTS.clear()
        _IN_FLIGHT = 0


__all__ = ["BUCKETS", "in_flight", "observe", "render", "reset"]
