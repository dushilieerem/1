"""因子批量回测异步任务注册表。

批量协调本身不能提交到 ``ExperimentManager``。协调器会等待两个因子
实验完成，如果它也占用 Manager 的 worker，就可能与两个子任务互相等待。
因此这里使用一个独立的单线程执行器，只负责批量编排；每个因子仍然交给
应用级 ``ExperimentManager`` 的两个 worker 执行。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from app.services.factor_backtest_batch.coordinator import (
    FactorBacktestBatchCoordinator,
    FactorBacktestBatchProfile,
)


FactorBacktestBatchTaskStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
]


class FactorBacktestBatchTaskRegistryClosedError(RuntimeError):
    """任务注册表已经停止接收新的批量回测。"""


@dataclass
class _BatchTask:
    task_id: str
    request_key: str | None
    coordinator: FactorBacktestBatchCoordinator
    profile: FactorBacktestBatchProfile
    force_retry: bool
    dry_run: bool
    progress_callback: Callable[[int, int], None] | None = None
    status: FactorBacktestBatchTaskStatus = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    batch_id: str | None = None
    batch_url: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


class FactorBacktestBatchTaskRegistry:
    """管理因子批量回测任务的进程内异步入口。

    注册表只保留任务快照，批次进度和因子结果仍以 SQLite repository 为准。
    ``retention_seconds`` 仅控制任务 ID 的内存保留时间，不影响数据库中的
    批次历史。
    """

    RETENTION_SECONDS = 60.0
    BATCH_URL_PREFIX = "/api/factor-backtest-batches/"
    POLL_URL_PREFIX = "/api/factor-backtest-batch-tasks/"

    def __init__(
        self,
        *,
        retention_seconds: float = RETENTION_SECONDS,
    ) -> None:
        if retention_seconds <= 0:
            raise ValueError("retention_seconds 必须大于 0")
        self.retention_seconds = float(retention_seconds)
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="svquant-factor-backtest-coordinator",
        )
        self._tasks: dict[str, _BatchTask] = {}
        self._dedupe: dict[str, str] = {}
        self._lock = threading.RLock()
        self._accepting = True
        self._shutdown = False

    @staticmethod
    def _request_key(
        profile: FactorBacktestBatchProfile,
        *,
        dry_run: bool,
    ) -> str:
        payload = {
            "profile": profile.to_dict(),
            "dry_run": dry_run,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _prune_locked(self, now: float | None = None) -> None:
        cutoff = (time.time() if now is None else now) - self.retention_seconds
        expired = [
            task_id
            for task_id, task in self._tasks.items()
            if task.status in {"succeeded", "failed"}
            and task.finished_at is not None
            and task.finished_at <= cutoff
        ]
        for task_id in expired:
            task = self._tasks.pop(task_id, None)
            if task is not None and task.request_key is not None:
                if self._dedupe.get(task.request_key) == task_id:
                    self._dedupe.pop(task.request_key, None)

    def submit(
        self,
        coordinator: FactorBacktestBatchCoordinator,
        profile: FactorBacktestBatchProfile,
        *,
        force_retry: bool = False,
        dry_run: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """提交批量编排任务并立即返回任务快照。

        ``force_retry`` 会绕过去重并创建新任务；其它相同请求在任务快照
        保留期间复用同一个 task ID。协调器由调用请求创建，注册表不保存
        跨请求的业务协调状态。
        """

        if not isinstance(coordinator, FactorBacktestBatchCoordinator):
            raise TypeError("coordinator 必须是 FactorBacktestBatchCoordinator")
        if not isinstance(profile, FactorBacktestBatchProfile):
            raise TypeError("profile 必须是 FactorBacktestBatchProfile")

        with self._lock:
            self._prune_locked()
            if not self._accepting:
                raise FactorBacktestBatchTaskRegistryClosedError(
                    "FactorBacktestBatchTaskRegistry 已关闭"
                )

            request_key = None if force_retry else self._request_key(
                profile,
                dry_run=dry_run,
            )
            if request_key is not None:
                existing_id = self._dedupe.get(request_key)
                if existing_id is not None and existing_id in self._tasks:
                    return self.snapshot(existing_id)  # type: ignore[return-value]

            task = _BatchTask(
                task_id=uuid.uuid4().hex,
                request_key=request_key,
                coordinator=coordinator,
                profile=profile,
                force_retry=force_retry,
                dry_run=dry_run,
                progress_callback=progress_callback,
            )
            self._tasks[task.task_id] = task
            if request_key is not None:
                self._dedupe[request_key] = task.task_id
            try:
                self._executor.submit(self._run_task, task.task_id)
            except BaseException:
                self._tasks.pop(task.task_id, None)
                if request_key is not None and self._dedupe.get(request_key) == task.task_id:
                    self._dedupe.pop(request_key, None)
                raise
            return self.snapshot(task.task_id)  # type: ignore[return-value]

    def _run_task(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = "running"
            task.started_at = time.time()

        try:
            result = task.coordinator.run_sync(
                task.profile,
                force_retry=task.force_retry,
                dry_run=task.dry_run,
                progress_callback=task.progress_callback,
            )
            if not isinstance(result, dict):
                raise TypeError("批量回测协调器必须返回 dict 结果")
        except BaseException as exc:  # noqa: BLE001 - task snapshot must retain failures
            with self._lock:
                current = self._tasks.get(task_id)
                if current is None:
                    return
                current.status = "failed"
                current.finished_at = time.time()
                current.error = f"{type(exc).__name__}: {exc}"
        else:
            batch_id = result.get("id")
            with self._lock:
                current = self._tasks.get(task_id)
                if current is None:
                    return
                batch_failed = result.get("status") == "failed"
                current.status = "failed" if batch_failed else "succeeded"
                current.finished_at = time.time()
                current.batch_id = str(batch_id) if batch_id else None
                current.batch_url = (
                    f"{self.BATCH_URL_PREFIX}{current.batch_id}"
                    if current.batch_id
                    else None
                )
                if batch_failed:
                    current.error = str(
                        result.get("error_message")
                        or result.get("error")
                        or "批量回测失败"
                    )
                current.result = dict(result)

    def snapshot(self, task_id: str) -> dict[str, Any] | None:
        """返回任务快照；过期或未知 task ID 返回 ``None``。"""

        with self._lock:
            self._prune_locked()
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return {
                "task_id": task.task_id,
                "status": task.status,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "finished_at": task.finished_at,
                "batch_id": task.batch_id,
                "batch_url": task.batch_url,
                "error": task.error,
                "result": dict(task.result) if task.result is not None else None,
            }

    def get(self, task_id: str) -> dict[str, Any] | None:
        """``snapshot`` 的语义化别名，供 HTTP 依赖使用。"""

        return self.snapshot(task_id)

    def shutdown(self, wait: bool = True) -> None:
        """停止接收新任务，并在需要时等待当前协调线程完成。"""

        with self._lock:
            if self._shutdown:
                return
            self._accepting = False
            self._shutdown = True
        self._executor.shutdown(wait=wait)

    close = shutdown

    @property
    def accepting(self) -> bool:
        with self._lock:
            return self._accepting


__all__ = [
    "FactorBacktestBatchTaskRegistry",
    "FactorBacktestBatchTaskRegistryClosedError",
    "FactorBacktestBatchTaskStatus",
]
