"""应用级实验调度器。

Manager 是进程内唯一的回测资源所有者。它只接受 ``Experiment`` 对象，
负责生命周期、有限容量、任务状态和 lane 标记；行情上下文由 Manager
创建并以只读形式传给实验。
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue
from typing import Any, Generic, Literal, TypeVar

from app.core.runtime import ResearchDataContext, ResearchRuntime
from app.services.experiment.base import Experiment, ExperimentContext


T = TypeVar("T")
Lane = Literal["interactive", "batch"]


class ExperimentManagerError(RuntimeError):
    """任务管理器基础异常。"""


class ExperimentQueueFullError(ExperimentManagerError):
    """线程池和排队容量均已用尽。"""


class ExperimentManagerClosedError(ExperimentManagerError):
    """任务管理器已经停止接收任务。"""


class ExperimentStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class _ExperimentRun(Generic[T]):
    run_id: str
    experiment: Experiment[T]
    key: str | None
    lane: Lane
    metadata: dict[str, Any]
    status: ExperimentStatus = ExperimentStatus.CREATED
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    future: Future[T] = field(default_factory=Future)
    result: T | None = None
    error: str | None = None
    cancel_requested: bool = False
    capacity_released: bool = False


class ExperimentHandle(Generic[T]):
    """提交任务后返回给调用方的轻量句柄。"""

    def __init__(self, manager: "ExperimentManager", run_id: str) -> None:
        self._manager = manager
        self.run_id = run_id

    @property
    def future(self) -> Future[T]:
        return self._manager._get_run(self.run_id).future

    @property
    def status(self) -> ExperimentStatus:
        return self._manager._get_run(self.run_id).status

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._manager._get_run(self.run_id).metadata)

    def result(self, timeout: float | None = None) -> T:
        return self.future.result(timeout=timeout)

    def cancel(self) -> bool:
        return self._manager.cancel(self.run_id)

    def snapshot(self, include_result: bool = False) -> dict[str, Any]:
        return self._manager.snapshot(self.run_id, include_result=include_result)


class ExperimentManager:
    """唯一的进程级实验执行边界。

    Manager 只维护一个普通 FIFO 队列。``lane`` 是任务元数据，批量窗口和
    交互任务的先后关系由上层业务在提交时控制，而不是由 Manager 插队。
    """

    _FINISHED_RETENTION_SECONDS = 60.0
    _TERMINAL_STATUSES = frozenset(
        {ExperimentStatus.SUCCEEDED, ExperimentStatus.FAILED, ExperimentStatus.CANCELLED}
    )
    _LANES = frozenset({"interactive", "batch"})

    def __init__(
        self,
        max_workers: int | None = None,
        max_queue_size: int | None = None,
        *,
        runtime: ResearchRuntime | None = None,
        data_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        self.max_workers = max_workers if max_workers is not None else self._env_int(
            "SVQUANT_EXPERIMENT_MAX_WORKERS", 2, minimum=1
        )
        self.max_queue_size = (
            max_queue_size
            if max_queue_size is not None
            else self._env_int("SVQUANT_EXPERIMENT_MAX_QUEUE_SIZE", 8, minimum=0)
        )
        if self.max_workers < 1:
            raise ValueError("max_workers 必须大于等于 1")
        if self.max_queue_size < 0:
            raise ValueError("max_queue_size 必须大于等于 0")
        if runtime is not None and data_dir is not None:
            raise ValueError("runtime 与 data_dir 不能同时指定")

        self.runtime = runtime or ResearchRuntime(data_dir=data_dir)
        self._capacity = threading.BoundedSemaphore(self.max_workers + self.max_queue_size)
        # semaphore 限制“运行中 + 等待中”的总数，Queue.maxsize 再把底层
        # 队列本身设为有界，避免未来新增提交路径绕过容量约束。
        self._queue: Queue[str | None] = Queue(
            maxsize=self.max_workers + self.max_queue_size
        )
        self._runs: dict[str, _ExperimentRun[Any]] = {}
        self._inflight: dict[str, str] = {}
        self._workers: list[threading.Thread] = []
        self._lock = threading.RLock()
        self._accepting = True
        self._started = False
        self._stopped = False
        self._reaper_stop = threading.Event()
        self._reaper = threading.Thread(
            target=self._reap_finished_runs,
            name="svquant-task-reaper",
            daemon=True,
        )
        self._reaper.start()

    @staticmethod
    def _env_int(name: str, default: int, *, minimum: int) -> int:
        try:
            value = int(os.environ.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(value, minimum)

    def start(self) -> "ExperimentManager":
        """启动 Manager worker；可重复调用。"""

        with self._lock:
            if not self._accepting:
                raise ExperimentManagerClosedError("ExperimentManager 已关闭")
            if self._started:
                return self
            self._started = True
            self._workers = [
                threading.Thread(
                    target=self._worker_loop,
                    name=f"svquant-backtest-{index}",
                    daemon=True,
                )
                for index in range(self.max_workers)
            ]
            for worker in self._workers:
                worker.start()
        return self

    def get_data_context(
        self,
        data_dir: str | os.PathLike[str] | None = None,
    ) -> ResearchDataContext:
        return self.runtime.get_context(data_dir)

    def submit(
        self,
        experiment: Experiment[T],
        *,
        key: str | None = None,
        lane: Lane = "interactive",
        metadata: dict[str, Any] | None = None,
    ) -> ExperimentHandle[T]:
        """提交一个具体 Experiment；普通 callable 会被拒绝。"""

        if not isinstance(experiment, Experiment):
            raise TypeError("ExperimentManager.submit 只接受 Experiment 对象")
        if lane not in self._LANES:
            raise ValueError("lane 必须为 'interactive' 或 'batch'")
        self.start()
        with self._lock:
            self._prune_finished_locked()
            if not self._accepting:
                raise ExperimentManagerClosedError("ExperimentManager 已关闭")
            if key is not None and (existing_id := self._inflight.get(key)) is not None:
                return ExperimentHandle(self, existing_id)
            if not self._capacity.acquire(blocking=False):
                raise ExperimentQueueFullError("回测任务队列已满，请稍后重试")

            run_id = uuid.uuid4().hex
            run = _ExperimentRun(
                run_id=run_id,
                experiment=experiment,
                key=key,
                lane=lane,
                metadata={**(metadata or {}), "lane": lane},
                status=ExperimentStatus.QUEUED,
            )
            self._runs[run_id] = run
            if key is not None:
                self._inflight[key] = run_id
            self._queue.put(run_id)
            return ExperimentHandle(self, run_id)

    def completed(
        self,
        result: T,
        *,
        key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExperimentHandle[T]:
        """创建已完成句柄，用于无需占用 worker 的缓存命中结果。"""

        with self._lock:
            self._prune_finished_locked()
            if key is not None and (existing_id := self._inflight.get(key)) is not None:
                return ExperimentHandle(self, existing_id)
            now = time.time()
            run_id = uuid.uuid4().hex
            future: Future[T] = Future()
            future.set_result(result)
            run = _ExperimentRun(
                run_id=run_id,
                experiment=_CompletedExperiment(result),
                key=key,
                lane="interactive",
                metadata=dict(metadata or {}),
                status=ExperimentStatus.SUCCEEDED,
                started_at=now,
                finished_at=now,
                future=future,
                result=result,
            )
            self._runs[run_id] = run
            return ExperimentHandle(self, run_id)

    def _worker_loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                if run_id is None:
                    return
                self._execute(run_id)
            finally:
                self._queue.task_done()

    def _execute(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            if run.status == ExperimentStatus.CANCELLED:
                self._release_capacity(run)
                return
            run.status = ExperimentStatus.RUNNING
            run.started_at = time.time()

        try:
            context = ExperimentContext(self.runtime.get_context())
            result = run.experiment.run(context)
        except BaseException as exc:  # noqa: BLE001 - Future 需要保留原异常
            with self._lock:
                run.status = ExperimentStatus.FAILED
                run.error = f"{type(exc).__name__}: {exc}"
                run.finished_at = time.time()
                self._finish_inflight(run)
                if not run.future.done():
                    run.future.set_exception(exc)
        else:
            with self._lock:
                run.status = ExperimentStatus.SUCCEEDED
                run.result = result
                run.finished_at = time.time()
                self._finish_inflight(run)
                if not run.future.done():
                    run.future.set_result(result)
        finally:
            with self._lock:
                self._release_capacity(run)

    def _release_capacity(self, run: _ExperimentRun[Any]) -> None:
        if not run.capacity_released:
            run.capacity_released = True
            self._capacity.release()

    def _finish_inflight(self, run: _ExperimentRun[Any]) -> None:
        if run.key is not None and self._inflight.get(run.key) == run.run_id:
            self._inflight.pop(run.key, None)

    def _prune_finished_locked(self, now: float | None = None) -> None:
        cutoff = (time.time() if now is None else now) - self._FINISHED_RETENTION_SECONDS
        for run_id in [
            run_id
            for run_id, run in self._runs.items()
            if run.status in self._TERMINAL_STATUSES
            and run.finished_at is not None
            and run.finished_at <= cutoff
        ]:
            run = self._runs.pop(run_id, None)
            if run is not None:
                run.result = None

    def _reap_finished_runs(self) -> None:
        while not self._reaper_stop.wait(5.0):
            with self._lock:
                self._prune_finished_locked()

    def _get_run(self, run_id: str) -> _ExperimentRun[Any]:
        with self._lock:
            self._prune_finished_locked()
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise KeyError(f"未找到实验任务: {run_id}") from exc

    def get(self, run_id: str) -> ExperimentHandle[Any] | None:
        with self._lock:
            self._prune_finished_locked()
            return ExperimentHandle(self, run_id) if run_id in self._runs else None

    def snapshot(self, run_id: str, *, include_result: bool = False) -> dict[str, Any]:
        run = self._get_run(run_id)
        payload: dict[str, Any] = {
            "run_id": run.run_id,
            "status": run.status.value,
            "lane": run.lane,
            "key": run.key,
            "metadata": dict(run.metadata),
            "created_at": run.created_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "error": run.error,
            "cancel_requested": run.cancel_requested,
        }
        if include_result:
            payload["result"] = run.result
        return payload

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            run = self._get_run(run_id)
            if run.status != ExperimentStatus.QUEUED:
                if run.status == ExperimentStatus.RUNNING:
                    # Manager 不强杀运行中的实验，只把取消意图投影给 API。
                    run.cancel_requested = True
                return False
            run.cancel_requested = True
            run.status = ExperimentStatus.CANCELLED
            run.finished_at = time.time()
            self._finish_inflight(run)
            self._release_capacity(run)
            return run.future.cancel()

    def shutdown(self, wait: bool = True, *, cancel_pending: bool = True) -> None:
        with self._lock:
            if self._stopped:
                return
            self._accepting = False
            if cancel_pending:
                for run in self._runs.values():
                    if run.status == ExperimentStatus.QUEUED:
                        run.cancel_requested = True
                        run.status = ExperimentStatus.CANCELLED
                        run.finished_at = time.time()
                        self._finish_inflight(run)
                        self._release_capacity(run)
                        run.future.cancel()
            self._stopped = True
            workers = list(self._workers)
            if self._started:
                for _ in workers:
                    self._queue.put(None)
        self._reaper_stop.set()
        if wait:
            for worker in workers:
                worker.join(timeout=5.0)
        self.runtime.close()

    def __enter__(self) -> "ExperimentManager":
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.shutdown()


class _CompletedExperiment(Experiment[T]):
    def __init__(self, result: T) -> None:
        self.result = result

    def run(self, context: ExperimentContext) -> T:
        return self.result


__all__ = [
    "ExperimentHandle",
    "ExperimentManager",
    "ExperimentManagerClosedError",
    "ExperimentManagerError",
    "ExperimentQueueFullError",
    "ExperimentStatus",
]
