# -*- coding: utf-8 -*-
"""量化因子长任务的队列模式（可选，默认仍走进程内线程池）。

`QUANT_FACTOR_JOB_MODE=queue` 时，API 只写 `background_jobs`，由独立
`worker.py` 进程消费；队列用 PostgreSQL `SKIP LOCKED`，可多实例/重启恢复。
"""
from __future__ import annotations

from typing import Any

from services.core.job_queue import enqueue, start_worker as start_queue_worker

RUN_KIND = "quant.factor.run"
RETRY_KIND = "quant.factor.retry_novelty"


def enqueue_run(uid: int, org: int, cid: str, phase: str, executor: str = "human", f0_run_id: str | None = None) -> int:
    return enqueue(RUN_KIND, {"uid": int(uid), "org": int(org), "cid": str(cid), "phase": str(phase),
                              "executor": str(executor or "human"), "f0_run_id": f0_run_id})


def enqueue_retry(uid: int, org: int, cid: str) -> int:
    return enqueue(RETRY_KIND, {"uid": int(uid), "org": int(org), "cid": str(cid)})


def _handle_run(payload: dict[str, Any]) -> dict[str, Any] | None:
    from . import service

    service.run(int(payload["uid"]), int(payload["org"]), str(payload["cid"]), str(payload["phase"]),
                str(payload.get("executor") or "human"), payload.get("f0_run_id"))
    return None


def _handle_retry(payload: dict[str, Any]) -> dict[str, Any] | None:
    from . import service

    service._retry_novelty(int(payload["uid"]), int(payload["org"]), str(payload["cid"]))
    return None


def start_worker(*, poll_sec: float = 2.0) -> None:
    start_queue_worker(RUN_KIND, _handle_run, poll_sec=poll_sec)
    start_queue_worker(RETRY_KIND, _handle_retry, poll_sec=poll_sec)


__all__ = ["RETRY_KIND", "RUN_KIND", "enqueue_retry", "enqueue_run", "start_worker"]
