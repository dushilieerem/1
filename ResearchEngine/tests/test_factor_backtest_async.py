"""因子回测异步任务 API 契约测试。"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.factor import runner
from app.schemas.backtest import FactorBacktestResponse
from app.services.experiment import Experiment, ExperimentContext
from app.services.experiment.manager import ExperimentManager


PAYLOAD = {
    "factor_code": "def score(self):\n    return self.close",
    "factor_name": "score",
}


class _StaticRuntime:
    def get_context(self, data_dir=None):
        return SimpleNamespace(data_engine=None, provider=None)

    def close(self):
        pass


class _ValueExperiment(Experiment[dict]):
    def __init__(self, value):
        self.value = value

    def run(self, context: ExperimentContext):
        return self.value


def _use_stub_runtime(application, *, max_workers=2, max_queue_size=8):
    application.state.experiment_manager.shutdown()
    manager = ExperimentManager(
        max_workers=max_workers,
        max_queue_size=max_queue_size,
        runtime=_StaticRuntime(),
    )
    application.state.experiment_manager = manager
    return manager


def _poll(client: TestClient, poll_url: str, *, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(poll_url)
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"任务轮询超时: {poll_url}")


def _successful_result() -> tuple[FactorBacktestResponse, str]:
    return FactorBacktestResponse(metrics={"annual_return": 0.12}), "BYPASS"


def test_post_returns_202_while_backtest_is_blocked(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def blocked_job(_request, **_kwargs):
        started.set()
        release.wait(timeout=3)
        return _successful_result()

    monkeypatch.setattr(runner, "_run_factor_backtest_job", blocked_job)
    app = create_app()
    _use_stub_runtime(app)
    try:
        with TestClient(app) as client:
            begin = time.perf_counter()
            response = client.post("/api/backtest/factor", json=PAYLOAD)
            elapsed = time.perf_counter() - begin

            assert response.status_code == 202
            assert elapsed < 0.5
            body = response.json()
            assert body["status"] in {"queued", "running"}
            assert response.headers["Location"] == body["poll_url"]
            assert response.headers["Retry-After"] == "1"
            assert started.wait(timeout=1)
            running = client.get(body["poll_url"]).json()
            assert running["status"] in {"queued", "running"}
            release.set()
            result = _poll(client, body["poll_url"])
            assert result["status"] == "succeeded"
            assert result["result"]["metrics"]["annual_return"] == 0.12
    finally:
        release.set()
        app.state.experiment_manager.shutdown()


def test_business_error_is_exposed_as_failed_task(monkeypatch):
    def failed_job(_request, **_kwargs):
        return FactorBacktestResponse(error="因子代码执行失败"), "BYPASS"

    monkeypatch.setattr(runner, "_run_factor_backtest_job", failed_job)
    app = create_app()
    _use_stub_runtime(app)
    with TestClient(app) as client:
        submission = client.post("/api/backtest/factor", json=PAYLOAD)
        result = _poll(client, submission.json()["poll_url"])

        assert result["status"] == "failed"
        assert result["error"] == "因子代码执行失败"
        assert result["result"] is None


def test_future_exception_is_exposed_as_failed_task(monkeypatch):
    def broken_job(_request, **_kwargs):
        raise RuntimeError("worker crashed")

    monkeypatch.setattr(runner, "_run_factor_backtest_job", broken_job)
    app = create_app()
    _use_stub_runtime(app)
    with TestClient(app) as client:
        submission = client.post("/api/backtest/factor", json=PAYLOAD)
        result = _poll(client, submission.json()["poll_url"])

        assert result["status"] == "failed"
        assert result["error"] == "RuntimeError: worker crashed"


def test_same_request_reuses_inflight_run_id(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def blocked_job(_request, **_kwargs):
        started.set()
        release.wait(timeout=3)
        return _successful_result()

    monkeypatch.setattr(runner, "_run_factor_backtest_job", blocked_job)
    app = create_app()
    _use_stub_runtime(app)
    try:
        with TestClient(app) as client:
            first = client.post("/api/backtest/factor", json=PAYLOAD)
            assert started.wait(timeout=1)
            second = client.post("/api/backtest/factor", json=PAYLOAD)

            assert first.status_code == second.status_code == 202
            assert first.json()["run_id"] == second.json()["run_id"]
            release.set()
            assert _poll(client, first.json()["poll_url"])["status"] == "succeeded"
    finally:
        release.set()
        app.state.experiment_manager.shutdown()


def test_queue_full_returns_429(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def blocked_job(_request, **_kwargs):
        started.set()
        release.wait(timeout=3)
        return _successful_result()

    monkeypatch.setattr(runner, "_run_factor_backtest_job", blocked_job)
    app = create_app()
    manager = ExperimentManager(max_workers=1, max_queue_size=0, runtime=_StaticRuntime())
    app.state.experiment_manager.shutdown()
    app.state.experiment_manager = manager
    try:
        with TestClient(app) as client:
            first = client.post("/api/backtest/factor", json=PAYLOAD)
            assert started.wait(timeout=1)
            rejected = client.post(
                "/api/backtest/factor",
                json={**PAYLOAD, "factor_name": "another_score"},
            )
            assert rejected.status_code == 429
            assert rejected.headers["Retry-After"] == "1"
            release.set()
            assert _poll(client, first.json()["poll_url"])["status"] == "succeeded"
    finally:
        release.set()
        app.state.experiment_manager.shutdown()


def test_closed_manager_returns_503():
    app = create_app()
    manager = app.state.experiment_manager
    manager.shutdown()
    client = TestClient(app)
    try:
        response = client.post("/api/backtest/factor", json=PAYLOAD)
        assert response.status_code == 503
    finally:
        client.close()
        manager.shutdown()


def test_queued_task_can_be_cancelled(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def blocked_job(_request, **_kwargs):
        started.set()
        release.wait(timeout=3)
        return _successful_result()

    monkeypatch.setattr(runner, "_run_factor_backtest_job", blocked_job)
    app = create_app()
    manager = ExperimentManager(max_workers=1, max_queue_size=1, runtime=_StaticRuntime())
    app.state.experiment_manager.shutdown()
    app.state.experiment_manager = manager
    try:
        with TestClient(app) as client:
            first = client.post("/api/backtest/factor", json=PAYLOAD)
            assert started.wait(timeout=1)
            queued_payload = {**PAYLOAD, "factor_name": "queued_score"}
            queued = client.post("/api/backtest/factor", json=queued_payload)
            poll_url = queued.json()["poll_url"]

            cancelled = client.delete(poll_url)
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"
            assert client.get(poll_url).json()["status"] == "cancelled"
            release.set()
            assert _poll(client, first.json()["poll_url"])["status"] == "succeeded"
    finally:
        release.set()
        app.state.experiment_manager.shutdown()


def test_running_task_records_cancel_request_without_killing_thread(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def blocked_job(_request, **_kwargs):
        started.set()
        release.wait(timeout=3)
        return _successful_result()

    monkeypatch.setattr(runner, "_run_factor_backtest_job", blocked_job)
    app = create_app()
    _use_stub_runtime(app)
    try:
        with TestClient(app) as client:
            submission = client.post("/api/backtest/factor", json=PAYLOAD)
            assert started.wait(timeout=1)
            poll_url = submission.json()["poll_url"]

            requested = client.delete(poll_url).json()
            assert requested["status"] == "running"
            assert requested["cancel_requested"] is True
            release.set()
            finished = _poll(client, poll_url)
            assert finished["status"] == "succeeded"
    finally:
        release.set()
        app.state.experiment_manager.shutdown()


def test_terminal_task_is_removed_after_60_seconds():
    manager = ExperimentManager(
        max_workers=1,
        max_queue_size=0,
        runtime=_StaticRuntime(),
    )
    try:
        handle = manager.submit(_ValueExperiment({"large": "result"}))
        assert handle.result(timeout=3) == {"large": "result"}
        with manager._lock:
            manager._runs[handle.run_id].finished_at -= 61
        assert manager.get(handle.run_id) is None
    finally:
        manager.shutdown()
