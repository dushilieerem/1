# -*- coding: utf-8 -*-
"""因子回测排队：HTTP 立刻返回 job_id，后台限流打 RE。

POST 不再同步干等 RE，避免短接口（建检测项目）被 Vite 打成 502。
RE 侧 FastAPI/Starlette 默认同步线程池约 40；本机 ThreadingHTTPServer
没有这个上限。这里的 inflight 只是 WebApp 自己的节流，别占满同事机。
可用环境变量 SVQUANT_RE_BACKTEST_INFLIGHT 覆盖。
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from services.factor.re_backtest_bff import forward_factor_backtest

# 同时打 RE 的路上限；其余 queued 等槽。默认 8（RE ~40 线程，留给面板/试算/同事）


def _max_inflight() -> int:
    raw = (os.environ.get("SVQUANT_RE_BACKTEST_INFLIGHT") or "8").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 8
    return max(1, min(n, 32))


MAX_INFLIGHT = _max_inflight()
JOB_TTL_SEC = 3600

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_pool = ThreadPoolExecutor(max_workers=MAX_INFLIGHT, thread_name_prefix="re-bt")


def _purge_locked(now: float) -> None:
    dead = [
        jid
        for jid, job in _jobs.items()
        if now - float(job.get("created_at") or 0) > JOB_TTL_SEC
        and str(job.get("status") or "") in {"done", "error", "cancelled"}
    ]
    for jid in dead:
        _jobs.pop(jid, None)


def queue_snapshot() -> dict[str, int]:
    with _lock:
        st = [str(j.get("status") or "") for j in _jobs.values()]
    return {
        "queued": sum(1 for s in st if s == "queued"),
        "running": sum(1 for s in st if s == "running"),
        "max_inflight": MAX_INFLIGHT,
    }


def submit_factor_backtest(payload: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    job: dict[str, Any] = {
        "job_id": job_id,
        "user_id": int(user_id),
        "status": "queued",
        "result": None,
        "error": None,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "cancel": False,
    }
    with _lock:
        _purge_locked(now)
        _jobs[job_id] = job
        queued = sum(1 for j in _jobs.values() if j.get("status") == "queued")
        running = sum(1 for j in _jobs.values() if j.get("status") == "running")
    _pool.submit(_run_job, job_id, payload)
    return {
        "ok": True,
        "async": True,
        "job_id": job_id,
        "status": "queued",
        "queued": queued,
        "running": running,
        "max_inflight": MAX_INFLIGHT,
    }


def get_factor_backtest_job(job_id: str, *, user_id: int) -> dict[str, Any]:
    with _lock:
        job = _jobs.get(str(job_id or "").strip())
        if not job:
            return {"ok": False, "error": "任务不存在或已过期", "status": "missing"}
        if int(job.get("user_id") or 0) != int(user_id):
            return {"ok": False, "error": "无权查看该任务", "status": "forbidden"}
        snap = {k: v for k, v in job.items() if k != "cancel"}
        snap["ok"] = True
        st = [str(j.get("status") or "") for j in _jobs.values()]
        snap["queued"] = sum(1 for s in st if s == "queued")
        snap["running"] = sum(1 for s in st if s == "running")
        snap["max_inflight"] = MAX_INFLIGHT
        return snap


def cancel_factor_backtest_job(job_id: str, *, user_id: int) -> dict[str, Any]:
    with _lock:
        job = _jobs.get(str(job_id or "").strip())
        if not job:
            return {"ok": False, "error": "任务不存在或已过期"}
        if int(job.get("user_id") or 0) != int(user_id):
            return {"ok": False, "error": "无权取消该任务"}
        st = str(job.get("status") or "")
        if st in {"done", "error"}:
            return {"ok": True, "status": st, "message": "已结束，无需取消"}
        job["cancel"] = True
        if st == "queued":
            job["status"] = "cancelled"
            job["finished_at"] = time.time()
        return {"ok": True, "status": job["status"]}


def _run_job(job_id: str, payload: dict[str, Any]) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job or job.get("cancel"):
            if job:
                job["status"] = "cancelled"
                job["finished_at"] = time.time()
            return
        job["status"] = "running"
        job["started_at"] = time.time()
    try:
        result = forward_factor_backtest(payload)
        with _lock:
            job = _jobs.get(job_id)
            if not job:
                return
            if job.get("cancel"):
                job["status"] = "cancelled"
                job["finished_at"] = time.time()
                return
            job["result"] = result
            job["status"] = "done"
            job["finished_at"] = time.time()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        with _lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job["error"] = str(exc)
            job["status"] = "error"
            job["finished_at"] = time.time()
