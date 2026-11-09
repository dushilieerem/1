# -*- coding: utf-8 -*-
"""数据 view → PG 同步的队列模式（可选）。

默认仍由部署机的 `scripts/ops/sync_data_production.sh` 直接跑；把
`SVQUANT_DATA_SYNC_VIA_QUEUE=1` 写进 deploy/.env 后，轮询只负责投递任务，
由 `worker.py` 消费：

- 失败可重试、进度和结果落在 `background_jobs`，不再只有一个日志文件；
- 与代码发布的轮询解耦，长同步不会占住部署锁。

生产库写入需要显式 `SVQUANT_DATA_SYNC_ALLOW_PRODUCTION=1`（worker 服务里配）。
"""
from __future__ import annotations

from typing import Any

from services.core.env_config import env
from services.core.job_queue import enqueue, start_worker as start_queue_worker

KIND = "data.sync"


def _allow_production() -> bool:
    return (env("SVQUANT_DATA_SYNC_ALLOW_PRODUCTION", "") or "").strip().lower() in {"1", "true", "yes"}


def enqueue_sync(view: str = "current", *, force: bool = False) -> int:
    return enqueue(KIND, {"view": str(view or "current"), "force": bool(force)})


def _handle(payload: dict[str, Any]) -> dict[str, Any]:
    from . import view_sync

    result = view_sync.sync_view(
        str(payload.get("view") or "current"),
        force=bool(payload.get("force")),
        allow_production=_allow_production(),
    )
    return {"status": result.get("status"), "view_id": result.get("view_id"), "rows": result.get("rows")}


def start_worker(*, poll_sec: float = 5.0) -> None:
    start_queue_worker(KIND, _handle, poll_sec=poll_sec)


__all__ = ["KIND", "enqueue_sync", "start_worker"]
