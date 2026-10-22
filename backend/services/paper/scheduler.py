# -*- coding: utf-8 -*-
"""模拟盘日终结算的进程内定时器。

与因子面板日更相同的套路：不依赖 cron/systemd，后端进程启动后由 daemon
线程定时轮询 ResearchEngine 的数据就绪状态，逐账户补结算。单 worker 部署
下不会重复；多进程部署由账户租约和数据库唯一索引兜底。
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

from services.core.env_config import env
from services.paper.settlement_service import enabled, run_scheduler_tick

DEFAULT_POLL_SEC = 300
MAX_SLEEP_SEC = 60
STARTUP_DELAY_SEC = 30

_thread: threading.Thread | None = None
_started = False
_lock = threading.Lock()
_last_result: dict | None = None


def _poll_sec() -> int:
    try:
        return max(30, int(env("SVQUANT_PAPER_POLL_SEC", str(DEFAULT_POLL_SEC)) or DEFAULT_POLL_SEC))
    except (TypeError, ValueError):
        return DEFAULT_POLL_SEC


def _loop() -> None:
    global _last_result
    time.sleep(STARTUP_DELAY_SEC)
    while True:
        try:
            if enabled():
                _last_result = run_scheduler_tick(reason="poll")
                if _last_result.get("settled"):
                    print(
                        f"[paper] {datetime.now():%Y-%m-%d %H:%M:%S} "
                        f"settled={_last_result.get('settled')} "
                        f"failed={_last_result.get('failed')}",
                        flush=True,
                    )
        except Exception as exc:  # noqa: BLE001 - 定时器不能因单轮失败退出
            _last_result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            print(f"[paper] scheduler tick failed: {exc}", flush=True)
        waited = 0
        while waited < _poll_sec():
            time.sleep(min(MAX_SLEEP_SEC, _poll_sec() - waited))
            waited += MAX_SLEEP_SEC


def start_paper_settlement_scheduler() -> None:
    global _thread, _started
    with _lock:
        if _started:
            return
        _started = True
        if not enabled():
            print("  paper trading scheduler 已关闭（SVQUANT_PAPER_TRADING_ENABLED=0）")
            return
        _thread = threading.Thread(
            target=_loop, name="paper-trading-scheduler", daemon=True
        )
        _thread.start()
        print(
            f"  paper trading scheduler 已启动（每 {_poll_sec()} 秒轮询数据就绪）"
        )


def last_result() -> dict | None:
    return _last_result


def _reset_for_tests() -> None:
    global _thread, _started, _last_result
    _thread = None
    _started = False
    _last_result = None


__all__ = [
    "last_result",
    "start_paper_settlement_scheduler",
    "_reset_for_tests",
]
