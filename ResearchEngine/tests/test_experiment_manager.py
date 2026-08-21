"""ExperimentManager 的并发边界、FIFO 顺序和任务生命周期测试。"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Callable, Generic, TypeVar

import pytest

from app.services.experiment import Experiment, ExperimentContext
from app.services.experiment.manager import (
    ExperimentManager,
    ExperimentQueueFullError,
    ExperimentStatus,
)


T = TypeVar("T")


class _FunctionExperiment(Experiment[T], Generic[T]):
    def __init__(self, fn: Callable[[], T]) -> None:
        self._fn = fn

    def run(self, context: ExperimentContext) -> T:
        return self._fn()


def _experiment(fn: Callable[[], T]) -> _FunctionExperiment[T]:
    return _FunctionExperiment(fn)


class _Runtime:
    def get_context(self, data_dir=None):
        return SimpleNamespace(data_engine=None, provider=None)

    def close(self):
        pass


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_manager_rejects_ordinary_callable():
    manager = ExperimentManager(max_workers=1, max_queue_size=0, runtime=_Runtime())
    try:
        with pytest.raises(TypeError, match="只接受 Experiment"):
            manager.submit(lambda: "not-an-experiment")
    finally:
        manager.shutdown()


def test_manager_limits_running_tasks_and_rejects_full_queue():
    manager = ExperimentManager(max_workers=2, max_queue_size=1, runtime=_Runtime())
    release = threading.Event()
    lock = threading.Lock()
    active = 0
    max_active = 0

    def blocking_task():
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        release.wait(timeout=3)
        with lock:
            active -= 1
        return "done"

    try:
        first = manager.submit(_experiment(blocking_task))
        second = manager.submit(_experiment(blocking_task))
        third = manager.submit(_experiment(lambda: "queued"))
        _wait_until(lambda: active == 2)

        with pytest.raises(ExperimentQueueFullError):
            manager.submit(_experiment(lambda: "rejected"))

        release.set()
        assert first.result(timeout=3) == "done"
        assert second.result(timeout=3) == "done"
        assert third.result(timeout=3) == "queued"
        assert max_active == 2
    finally:
        release.set()
        manager.shutdown()


def test_manager_reuses_same_inflight_key():
    manager = ExperimentManager(max_workers=1, max_queue_size=1, runtime=_Runtime())
    calls = 0
    lock = threading.Lock()

    def task():
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.05)
        return 42

    try:
        first = manager.submit(_experiment(task), key="same-request")
        second = manager.submit(_experiment(task), key="same-request")
        assert first.run_id == second.run_id
        assert first.result(timeout=3) == 42
        assert second.result(timeout=3) == 42
        assert calls == 1
    finally:
        manager.shutdown()


def test_manager_can_cancel_queued_task():
    manager = ExperimentManager(max_workers=1, max_queue_size=1, runtime=_Runtime())
    release = threading.Event()

    try:
        running = manager.submit(
            _experiment(lambda: (release.wait(timeout=3), "running")[1])
        )
        queued = manager.submit(_experiment(lambda: "never"))
        _wait_until(lambda: running.status == ExperimentStatus.RUNNING)

        assert queued.cancel() is True
        assert queued.status == ExperimentStatus.CANCELLED
        release.set()
        assert running.result(timeout=3) == "running"
    finally:
        release.set()
        manager.shutdown()


def test_manager_is_a_normal_fifo_queue():
    manager = ExperimentManager(max_workers=1, max_queue_size=3, runtime=_Runtime())
    release = threading.Event()
    order: list[str] = []

    try:
        first = manager.submit(
            _experiment(lambda: (release.wait(timeout=3), "batch-1")[1]),
            lane="batch",
        )
        _wait_until(lambda: first.status == ExperimentStatus.RUNNING)
        batch_two = manager.submit(
            _experiment(lambda: order.append("batch-2") or "batch-2"),
            lane="batch",
        )
        interactive = manager.submit(
            _experiment(lambda: order.append("interactive") or "interactive"),
            lane="interactive",
        )
        batch_three = manager.submit(
            _experiment(lambda: order.append("batch-3") or "batch-3"),
            lane="batch",
        )

        release.set()
        assert first.result(timeout=3) == "batch-1"
        assert batch_two.result(timeout=3) == "batch-2"
        assert interactive.result(timeout=3) == "interactive"
        assert batch_three.result(timeout=3) == "batch-3"
        assert order == ["batch-2", "interactive", "batch-3"]
    finally:
        release.set()
        manager.shutdown()
