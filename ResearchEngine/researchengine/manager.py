"""ResearchEngine 回测任务管理。

``ExperimentManager`` 是 ResearchEngine 进程内的回测执行边界：

* 持有自己的线程池，而不是把回测交给 FastAPI/AnyIO 的通用线程池；
* 用有界容量保护进程内存，避免请求无限排队；
* 记录一次回测任务的生命周期，并复用相同任务键的并发请求；
* 只编排可执行任务，不参与因子、收益或指标计算。

旧版的 ``create/run/run_all`` API 仍保留，用于兼容直接使用 ``Experiment``
的研究代码；HTTP 回测通过 ``submit`` 进入同一个执行边界。
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

from quantcore import BaseFactor

from researchengine.config import ConfigManager
from researchengine.experiment import Experiment
from researchengine.result.manager import ResultManager


T = TypeVar("T")


class ExperimentManagerError(RuntimeError):
    """任务管理器基础异常。"""


class ExperimentQueueFullError(ExperimentManagerError):
    """线程池和排队容量均已用尽。"""


class ExperimentManagerClosedError(ExperimentManagerError):
    """任务管理器已经停止接收任务。"""


class ExperimentStatus(str, Enum):
    """一次回测任务的状态。"""

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class _ExperimentRun(Generic[T]):
    run_id: str
    key: str | None
    metadata: dict[str, Any]
    status: ExperimentStatus = ExperimentStatus.CREATED
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    future: Future[T] | None = None
    result: T | None = None
    error: str | None = None
    cancel_requested: bool = False


class ExperimentHandle(Generic[T]):
    """提交任务后返回给调用方的轻量句柄。"""

    def __init__(self, manager: "ExperimentManager", run_id: str) -> None:
        self._manager = manager
        self.run_id = run_id

    @property
    def future(self) -> Future[T]:
        run = self._manager._get_run(self.run_id)
        if run.future is None:
            raise ExperimentManagerError(f"任务 {self.run_id} 尚未绑定 Future")
        return run.future

    @property
    def status(self) -> ExperimentStatus:
        return self._manager._get_run(self.run_id).status

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._manager._get_run(self.run_id).metadata)

    def result(self, timeout: float | None = None) -> T:
        """同步等待任务结果；HTTP 层应使用 ``asyncio.wrap_future`` 等待。"""

        return self.future.result(timeout=timeout)

    def cancel(self) -> bool:
        """取消仍在排队的任务；运行中的线程只能记录取消请求。"""

        return self._manager.cancel(self.run_id)

    def snapshot(self, include_result: bool = False) -> dict[str, Any]:
        return self._manager.snapshot(self.run_id, include_result=include_result)


class ExperimentManager:
    """ResearchEngine 进程内的回测任务调度器。

    ``max_workers`` 控制同时执行的回测数，``max_queue_size`` 控制额外排队
    的任务数。默认值偏保守，因为一次回测通常会加载较大的行情面板。
    """

    def __init__(
        self,
        max_workers: int | None = None,
        max_queue_size: int | None = None,
    ) -> None:
        self.max_workers = (
            max_workers
            if max_workers is not None
            else self._env_int("SVQUANT_EXPERIMENT_MAX_WORKERS", 2, minimum=1)
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

        self.experiments: Dict[str, Experiment] = {}
        self._lock = threading.RLock()
        self._capacity = threading.BoundedSemaphore(
            self.max_workers + self.max_queue_size
        )
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="svquant-backtest",
        )
        self._runs: dict[str, _ExperimentRun[Any]] = {}
        self._inflight: dict[str, str] = {}
        self._accepting = True

    @staticmethod
    def _env_int(name: str, default: int, *, minimum: int) -> int:
        try:
            value = int(os.environ.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(value, minimum)

    def start(self) -> "ExperimentManager":
        """启动生命周期钩子。

        线程池由构造函数建立，但线程只会在第一次提交任务时创建。保留这个
        显式方法是为了让 FastAPI lifespan 成为资源所有权的清晰入口。
        """

        with self._lock:
            if not self._accepting:
                raise ExperimentManagerClosedError("ExperimentManager 已关闭")
        return self

    def submit(
        self,
        task: Callable[[], T],
        *,
        key: str | None = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExperimentHandle[T]:
        """提交一个回测任务。

        当 ``key`` 已有任务在执行或排队时，返回同一个任务句柄，不重复占用
        线程。没有空闲容量时立即抛出 ``ExperimentQueueFullError``。
        """

        with self._lock:
            if not self._accepting:
                raise ExperimentManagerClosedError("ExperimentManager 已关闭")
            if key is not None:
                existing_id = self._inflight.get(key)
                if existing_id is not None:
                    return ExperimentHandle(self, existing_id)
            if not self._capacity.acquire(blocking=False):
                raise ExperimentQueueFullError("回测任务队列已满，请稍后重试")

            run_id = uuid.uuid4().hex
            run = _ExperimentRun[T](
                run_id=run_id,
                key=key,
                metadata=dict(metadata or {}),
                status=ExperimentStatus.QUEUED,
            )
            self._runs[run_id] = run
            if key is not None:
                self._inflight[key] = run_id
            try:
                run.future = self._executor.submit(self._execute, run_id, task)
            except Exception:
                self._runs.pop(run_id, None)
                if key is not None and self._inflight.get(key) == run_id:
                    self._inflight.pop(key, None)
                self._capacity.release()
                raise
            return ExperimentHandle(self, run_id)

    def completed(
        self,
        result: T,
        *,
        key: str | None = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExperimentHandle[T]:
        """创建已完成句柄，用于缓存命中等无需占用线程的结果。"""

        with self._lock:
            if key is not None:
                existing_id = self._inflight.get(key)
                if existing_id is not None:
                    return ExperimentHandle(self, existing_id)
            now = time.time()
            run_id = uuid.uuid4().hex
            future: Future[T] = Future()
            future.set_result(result)
            self._runs[run_id] = _ExperimentRun(
                run_id=run_id,
                key=key,
                metadata=dict(metadata or {}),
                status=ExperimentStatus.SUCCEEDED,
                started_at=now,
                finished_at=now,
                future=future,
                result=result,
            )
            return ExperimentHandle(self, run_id)

    def _execute(self, run_id: str, task: Callable[[], T]) -> T:
        with self._lock:
            run = self._runs[run_id]
            if run.status == ExperimentStatus.CANCELLED:
                self._capacity.release()
                raise ExperimentManagerError(f"任务 {run_id} 已取消")
            run.status = ExperimentStatus.RUNNING
            run.started_at = time.time()

        try:
            result = task()
        except BaseException as exc:
            with self._lock:
                run.status = ExperimentStatus.FAILED
                run.error = f"{type(exc).__name__}: {exc}"
                run.finished_at = time.time()
                self._finish_inflight(run)
            raise
        else:
            with self._lock:
                run.status = ExperimentStatus.SUCCEEDED
                run.result = result
                run.finished_at = time.time()
                self._finish_inflight(run)
            return result
        finally:
            self._capacity.release()

    def _finish_inflight(self, run: _ExperimentRun[Any]) -> None:
        if run.key is not None and self._inflight.get(run.key) == run.run_id:
            self._inflight.pop(run.key, None)

    def _get_run(self, run_id: str) -> _ExperimentRun[Any]:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as exc:
                raise KeyError(f"未找到回测任务: {run_id}") from exc

    def get(
        self, identifier: str
    ) -> ExperimentHandle[Any] | Experiment | None:
        """按 run_id 查询任务；按旧实验名查询已登记 Experiment。"""
        with self._lock:
            if identifier in self._runs:
                return ExperimentHandle(self, identifier)
            return self.experiments.get(identifier)

    def snapshot(self, run_id: str, *, include_result: bool = False) -> dict[str, Any]:
        run = self._get_run(run_id)
        with self._lock:
            snapshot: dict[str, Any] = {
                "run_id": run.run_id,
                "status": run.status.value,
                "metadata": dict(run.metadata),
                "created_at": run.created_at,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "error": run.error,
                "cancel_requested": run.cancel_requested,
            }
            if include_result and run.status == ExperimentStatus.SUCCEEDED:
                snapshot["result"] = run.result
            return snapshot

    def cancel(self, run_id: str) -> bool:
        run = self._get_run(run_id)
        with self._lock:
            if run.status in {
                ExperimentStatus.SUCCEEDED,
                ExperimentStatus.FAILED,
                ExperimentStatus.CANCELLED,
            }:
                return False
            if run.future is not None and run.future.cancel():
                run.status = ExperimentStatus.CANCELLED
                run.finished_at = time.time()
                self._finish_inflight(run)
                self._capacity.release()
                return True
            # 任务已经进入线程后不能安全强杀；记录请求，实际执行仍会完成。
            run.cancel_requested = True
            return False

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = True) -> None:
        """停止接收任务，取消尚未开始的任务并关闭线程池。"""

        with self._lock:
            if not self._accepting:
                return
            self._accepting = False
            pending = [
                run.run_id
                for run in self._runs.values()
                if run.status == ExperimentStatus.QUEUED
            ]
        if cancel_pending:
            for run_id in pending:
                self.cancel(run_id)
        self._executor.shutdown(wait=wait, cancel_futures=cancel_pending)

    def create(
        self,
        factor: BaseFactor,
        universe: str = "CSI500",
        start: str = "2020-01-01",
        end: str = "2024-12-31",
        config: Optional[ConfigManager] = None,
    ) -> Experiment:
        """创建并登记一个旧版 ``Experiment``，保留兼容入口。"""

        exp = Experiment(
            factor=factor,
            universe=universe,
            start_date=start,
            end_date=end,
            config=config,
        )
        with self._lock:
            self.experiments[factor.name] = exp
        return exp

    def run(self, experiment: Experiment) -> ResultManager:
        """通过 Manager 自己的线程池运行一个旧版实验。"""

        return self.submit(experiment.run, key=f"legacy:{id(experiment)}").result()

    def run_all(self) -> Dict[str, ResultManager]:
        """并行运行已登记实验，并按登记名称返回结果。"""

        with self._lock:
            items = list(self.experiments.items())
        handles = {
            name: self.submit(exp.run, key=f"legacy:{id(exp)}")
            for name, exp in items
        }
        return {name: handle.result() for name, handle in handles.items()}

    def __enter__(self) -> "ExperimentManager":
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.shutdown()


__all__ = [
    "ExperimentHandle",
    "ExperimentManager",
    "ExperimentManagerClosedError",
    "ExperimentManagerError",
    "ExperimentQueueFullError",
    "ExperimentStatus",
]
