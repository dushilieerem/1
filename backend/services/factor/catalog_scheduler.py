# -*- coding: utf-8 -*-
"""因子目录定时同步（P1-F04）：primary/all 双 scope。

与 `dashboard_scheduler` / `news_ingest` 同一套路：后端进程内 daemon 线程，
不依赖 cron / systemd。启动时 `warm_re_catalog_async()` 负责首轮预热，
本定时器只负责后续轮次。

配置（backend/.env，均可省略）：
  RE_CATALOG_SYNC_ENABLED=1          # 置 0 关闭
  RE_CATALOG_SYNC_INTERVAL_SEC=86400 # 同步间隔秒；<=0 关闭
"""
from __future__ import annotations

import threading
import time
from typing import Any

DEFAULT_INTERVAL_SEC = 86400

_lock = threading.Lock()
_thread: threading.Thread | None = None
_started = False


def _enabled() -> bool:
    from services.core.env_config import env

    return (env("RE_CATALOG_SYNC_ENABLED", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _interval() -> int:
    from services.core.env_config import env

    raw = env("RE_CATALOG_SYNC_INTERVAL_SEC", str(DEFAULT_INTERVAL_SEC))
    try:
        return int(raw or DEFAULT_INTERVAL_SEC)
    except (TypeError, ValueError):
        return -1


def sync_once() -> dict[str, Any]:
    """同步 primary/all 两个 scope，并打印一致性结果（多实例互斥）。"""
    from services.core.distributed_lock import advisory_lock
    from services.factor.re_factor_catalog import sync_all_scopes

    with advisory_lock("svquant:re-catalog:sync") as acquired:
        if not acquired:
            print("  re-catalog 同步跳过：另一实例正在同步", flush=True)
            return {"ok": False, "skipped": True}
        out = sync_all_scopes()
    consistency = out.get("consistency") or {}
    warnings = list(consistency.get("warnings") or [])
    errors = list(out.get("errors") or [])
    print(
        f"  re-catalog 同步：ok={out.get('ok')} warnings={warnings} errors={errors}",
        flush=True,
    )
    if not out.get("ok"):
        # P1-F04：陈旧/失败/双 scope 不一致都在这里留一条醒目告警
        print(
            "  re-catalog 同步告警：" + ("; ".join(warnings + errors) or "未知原因"),
            flush=True,
        )
    return out


def start_re_catalog_sync_scheduler() -> None:
    """启动目录定时同步线程（幂等）。RE_CATALOG_SYNC_ENABLED=0 关闭。"""
    global _thread, _started

    if not _enabled():
        print("  re-catalog 定时同步：已关闭（RE_CATALOG_SYNC_ENABLED=0）")
        return
    interval = _interval()
    if interval <= 0:
        print("  re-catalog 定时同步：间隔非法，跳过")
        return

    with _lock:
        if _started:
            return
        _started = True

    # P1-O06：调度入队，worker 在任意实例执行
    from services.core.job_queue import enqueue, start_worker

    start_worker("re.catalog.sync", lambda _payload: sync_once(), poll_sec=30)

    def _loop() -> None:
        while True:
            time.sleep(interval)
            try:
                enqueue("re.catalog.sync", {})
            except Exception as exc:  # noqa: BLE001
                print(f"  re-catalog 入队失败: {exc}", flush=True)

    _thread = threading.Thread(target=_loop, name="re-catalog-sync", daemon=True)
    _thread.start()
    print(f"  re-catalog 定时同步：每 {interval}s 同步一次")
