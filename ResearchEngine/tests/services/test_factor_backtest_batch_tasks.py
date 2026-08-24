"""因子批量回测异步提交、任务状态和生命周期测试。"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.factor_backtest_batch import (
    FactorBacktestBatchCoordinator,
    FactorBacktestBatchProfile,
    FactorBacktestBatchTaskRegistry,
)


def _wait_for_status(client: TestClient, task_id: str, expected: set[str]) -> dict:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        response = client.get(f"/api/factor-backtest-batch-tasks/{task_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in expected:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"任务未在期限内进入 {expected}: {task_id}")


def test_task_registry_deduplicates_force_retry_and_keeps_batch_mapping():
    started = threading.Event()
    release = threading.Event()
    calls = {"count": 0}

    def run_sync(profile, *, force_retry=False, dry_run=False, progress_callback=None):
        calls["count"] += 1
        started.set()
        release.wait(timeout=5)
        return {"id": f"batch-{calls['count']}", "status": "completed"}

    coordinator = FactorBacktestBatchCoordinator(SimpleNamespace())
    coordinator.run_sync = run_sync  # type: ignore[method-assign]
    profile = FactorBacktestBatchProfile("2026-08-19")
    registry = FactorBacktestBatchTaskRegistry()
    try:
        first = registry.submit(coordinator, profile)
        repeated = registry.submit(coordinator, profile)
        forced = registry.submit(coordinator, profile, force_retry=True)

        assert first["status"] == "queued"
        assert repeated["task_id"] == first["task_id"]
        assert forced["task_id"] != first["task_id"]
        assert started.wait(timeout=2)

        release.set()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            snapshot = registry.get(forced["task_id"])
            if snapshot and snapshot["status"] == "succeeded":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("force_retry 任务没有完成")

        first_done = registry.get(first["task_id"])
        forced_done = registry.get(forced["task_id"])
        assert first_done["batch_id"] == "batch-1"
        assert first_done["batch_url"] == "/api/factor-backtest-batches/batch-1"
        assert forced_done["batch_id"] == "batch-2"
        assert calls["count"] == 2
    finally:
        release.set()
        registry.shutdown()


def test_batch_http_submission_is_immediate_and_maps_batch_id(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    coordinators: list[int] = []

    def run_sync(self, profile, *, force_retry=False, dry_run=False, progress_callback=None):
        coordinators.append(id(self))
        started.set()
        release.wait(timeout=5)
        return {
            "id": f"batch-{len(coordinators)}",
            "status": "completed",
            "total_count": 0,
        }

    monkeypatch.setattr(FactorBacktestBatchCoordinator, "run_sync", run_sync)
    application = create_app()
    with TestClient(application) as client:
        response = client.post(
            "/api/internal/factor-backtest-batches",
            json={"as_of_date": "2026-08-19"},
        )
        assert response.status_code == 202
        submission = response.json()
        assert submission["status"] == "queued"
        assert submission["task_id"]
        assert submission["poll_url"].endswith(submission["task_id"])
        assert started.wait(timeout=2)

        repeated = client.post(
            "/api/internal/factor-backtest-batches",
            json={"as_of_date": "2026-08-19"},
        )
        forced = client.post(
            "/api/internal/factor-backtest-batches",
            json={"as_of_date": "2026-08-19", "force_retry": True},
        )
        assert repeated.status_code == 202
        assert forced.status_code == 202
        assert repeated.json()["task_id"] == submission["task_id"]
        assert forced.json()["task_id"] != submission["task_id"]

        release.set()
        completed = _wait_for_status(client, submission["task_id"], {"succeeded"})
        assert completed["batch_id"] == "batch-1"
        assert completed["batch_url"] == "/api/factor-backtest-batches/batch-1"
        _wait_for_status(client, forced.json()["task_id"], {"succeeded"})
        assert len(set(coordinators)) == 2


def test_dry_run_task_has_no_persistent_batch_mapping(monkeypatch):
    def run_sync(self, profile, *, force_retry=False, dry_run=False, progress_callback=None):
        assert dry_run is True
        return {"status": "dry_run", "preflight": {"factor_count": 0}}

    monkeypatch.setattr(FactorBacktestBatchCoordinator, "run_sync", run_sync)
    application = create_app()
    with TestClient(application) as client:
        response = client.post(
            "/api/internal/factor-backtest-batches",
            json={"as_of_date": "2026-08-19", "dry_run": True},
        )
        assert response.status_code == 202
        task = _wait_for_status(client, response.json()["task_id"], {"succeeded"})
        assert task["batch_id"] is None
        assert task["batch_url"] is None
        assert task["result"]["status"] == "dry_run"


def test_batch_routes_are_replaced_without_old_compatibility_paths():
    application = create_app()
    with TestClient(application) as client:
        assert client.get("/api/factor-backtests/batches").status_code == 404
        assert client.post(
            "/api/internal/factor-backtests/batches",
            json={"as_of_date": "2026-08-19"},
        ).status_code == 404
        assert client.get("/api/factor-backtest-batch-tasks/unknown").status_code == 404


def test_lifespan_closes_batch_registry_before_manager(monkeypatch):
    application = create_app()
    events: list[str] = []
    registry = application.state.factor_backtest_batch_task_registry
    manager = application.state.experiment_manager
    original_registry_shutdown = registry.shutdown
    original_manager_shutdown = manager.shutdown

    def close_registry(*, wait=True):
        events.append("registry")
        return original_registry_shutdown(wait=wait)

    def close_manager(*args, **kwargs):
        events.append("manager")
        return original_manager_shutdown(*args, **kwargs)

    monkeypatch.setattr(registry, "shutdown", close_registry)
    monkeypatch.setattr(manager, "shutdown", close_manager)
    with TestClient(application):
        pass
    assert events == ["registry", "manager"]
