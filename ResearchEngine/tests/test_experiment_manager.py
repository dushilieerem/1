"""ExperimentManager 的并发边界和任务生命周期测试。"""

from __future__ import annotations

import threading
import time

import pytest

from researchengine.manager import (
    ExperimentManager,
    ExperimentQueueFullError,
    ExperimentStatus,
)


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_manager_limits_running_tasks_and_rejects_full_queue():
    manager = ExperimentManager(max_workers=2, max_queue_size=1)
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
        first = manager.submit(blocking_task)
        second = manager.submit(blocking_task)
        third = manager.submit(lambda: "queued")
        _wait_until(lambda: active == 2)

        with pytest.raises(ExperimentQueueFullError):
            manager.submit(lambda: "rejected")

        release.set()
        assert first.result(timeout=3) == "done"
        assert second.result(timeout=3) == "done"
        assert third.result(timeout=3) == "queued"
        assert max_active == 2
    finally:
        release.set()
        manager.shutdown()


def test_manager_reuses_same_inflight_key():
    manager = ExperimentManager(max_workers=1, max_queue_size=1)
    calls = 0
    lock = threading.Lock()

    def task():
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.05)
        return 42

    try:
        first = manager.submit(task, key="same-request")
        second = manager.submit(task, key="same-request")
        assert first.run_id == second.run_id
        assert first.result(timeout=3) == 42
        assert second.result(timeout=3) == 42
        assert calls == 1
    finally:
        manager.shutdown()


def test_manager_can_cancel_queued_task():
    manager = ExperimentManager(max_workers=1, max_queue_size=1)
    release = threading.Event()

    try:
        running = manager.submit(lambda: (release.wait(timeout=3), "running")[1])
        queued = manager.submit(lambda: "never")
        _wait_until(lambda: running.status == ExperimentStatus.RUNNING)

        assert queued.cancel() is True
        assert queued.status == ExperimentStatus.CANCELLED
        release.set()
        assert running.result(timeout=3) == "running"
    finally:
        release.set()
        manager.shutdown()

