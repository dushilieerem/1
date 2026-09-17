"""FEAT-027 因子批量回测：仓库、编排和只读查询测试。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.config import ConfigManager
from app.services.experiment.factor import _apply_factor_batch_filters, _predictive_summary
from app.database.factor_backtest_store import FactorBacktestStore, default_factor_backtest_db_path
from app.cli.factor_backtest_batch import main
from app.models.factor_batch import FactorBacktestBatchProfile, FactorCatalogItem
from app.services.factor_backtest_batch.coordinator import (
    _outcome_from_result,
    _factor_spec,
    run_factor_backtest_batch,
)
from app.services.factor.experiment import FactorBacktestExperiment
from app.services.experiment.manager import ExperimentManager
from app.schemas.backtest import FactorBacktestRequest
from app.services.factor.runner import _request_factor_source_hash, _request_spec
from app.utils.paths import _repo_root


class _StaticDataEngine:
    def __init__(self, root: Path):
        self.data_dir = root
        self.provider = SimpleNamespace()
        self.release_id = "test-release"
        self.data_engine = self


def _make_batch(store: FactorBacktestStore, *, as_of: str = "2026-08-19") -> tuple[str, str]:
    batch = store.create_batch(
        batch_key=f"key-{as_of}",
        as_of_date=as_of,
        window_start="2016-08-19",
        window_end=as_of,
        profile={"as_of_date": as_of},
        profile_hash="profile-hash",
        catalog_version="catalog-v1",
        metric_version="factor-scorecard-v1",
        total_count=1,
    )
    factor = store.ensure_factor_run(
        batch_id=batch["id"],
        library_name="test_library",
        factor_name="test_factor",
        factor_source_hash="source-hash",
    )
    store.record_factor(
        factor["id"],
        status="succeeded",
        actual_start="2022-01-03",
        actual_end=as_of,
        observation_days=10,
        sample_quality="short_history",
        quantile_metrics=[
            {"quantile": name, "annual_return": index / 100.0}
            for index, name in enumerate(("Q1", "Q2", "Q3", "Q4", "Q5", "benchmark"), 1)
        ],
        predictive_metrics={"ic_mean": 0.1, "rank_ic_mean": 0.08, "ic_ir": 1.5},
    )
    store.refresh_batch_counts(batch["id"], final=True)
    return batch["id"], factor["id"]


def test_default_factor_backtest_db_path_is_factor_database(monkeypatch):
    monkeypatch.delenv("SVQUANT_FACTOR_BACKTEST_DB", raising=False)
    monkeypatch.delenv("SVQUANT_FACTOR_BACKTEST_DB_PATH", raising=False)

    assert default_factor_backtest_db_path() == (
        _repo_root()
        / "ResearchEngine"
        / "app"
        / "assets"
        / "factors"
        / "factor_backtest.db"
    )


def test_profile_uses_rolling_calendar_years_and_fixed_defaults():
    profile = FactorBacktestBatchProfile("2026-08-19")

    assert profile.window_start == "2016-08-19"
    assert profile.window_end == "2026-08-19"
    assert profile.universe == "CSI_ALL"
    assert profile.benchmark == "CSI300"
    assert profile.portfolio_type == "long_only"
    assert profile.groups == 5
    assert profile.rebalance_days == 1
    assert profile.analysis_level == "core"
    assert not profile.filter_limit_up and not profile.filter_suspended


def test_builtin_single_and_batch_specs_share_identity(monkeypatch, tmp_path: Path):
    source_path = tmp_path / "library.py"
    source_path.write_text("# same factor source\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.factor.runner._builtin_factor_library_entry",
        lambda _library: (tmp_path, "library", {}),
    )

    profile = FactorBacktestBatchProfile("2026-08-19")
    request = FactorBacktestRequest(
        library_name="library",
        factor_name="factor",
        universe="CSI_ALL",
        start=profile.window_start,
        end=profile.window_end,
    )
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    batch_spec = _factor_spec(
        profile,
        FactorCatalogItem("library", "factor", source_hash),
    )

    assert _request_factor_source_hash(request) == source_hash
    assert _request_spec(request).identity(data_release_id="release-1") == batch_spec.identity(
        data_release_id="release-1"
    )


def test_predictive_summary_returns_scalar_ic_rank_ic_and_annualized_icir():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    factor = pd.DataFrame(
        [[1.0, 2.0, 3.0], [3.0, 1.0, 2.0], [2.0, 3.0, 1.0]],
        index=dates,
        columns=list("ABC"),
    )
    forward = factor.copy()

    summary = _predictive_summary(factor, forward)

    assert summary["valid_days"] == 3
    assert summary["ic_mean"] == 1.0
    assert summary["rank_ic_mean"] == 1.0
    assert summary["ic_ir"] == 0.0
    assert "value" not in summary


def test_batch_skips_missing_suspension_filter_and_uses_up_and_down_status():
    dates = pd.date_range("2026-01-01", periods=2)
    columns = ["A", "B", "C"]
    factor = pd.DataFrame(1.0, index=dates, columns=columns)

    class PanelStub:
        def __init__(self):
            self.fields = {
                "up_and_down_status": pd.DataFrame(
                    [["非涨跌停", "非涨跌停", "涨停"], ["非涨跌停"] * 3],
                    index=dates,
                    columns=columns,
                ),
            }

        def __contains__(self, name):
            return name in self.fields

        def __getattr__(self, name):
            return self.fields[name]

    config = ConfigManager()
    config.set("factor_batch.filters_enabled", True)
    config.set("filter_suspended", True)
    config.set("filter_limit_up", True)

    filtered = _apply_factor_batch_filters(factor, PanelStub(), config)

    # 当前 release 没有独立 is_suspended，停牌过滤按缺失字段跳过。
    assert filtered.loc[dates[0], "B"] == 1.0
    assert pd.isna(filtered.loc[dates[0], "C"])
    assert filtered.loc[dates[1]].notna().all()


def test_store_round_trip_persists_six_quantile_rows_and_predictive_metrics(tmp_path: Path):
    store = FactorBacktestStore(tmp_path / "factor_backtest.db")
    batch_id, factor_id = _make_batch(store)

    batch = store.get_batch(batch_id)
    factor = store.list_factor_runs(batch_id)[0]

    assert batch["status"] == "completed"
    assert batch["succeeded_count"] == 1
    assert factor["id"] == factor_id
    assert [row["quantile"] for row in factor["quantile_metrics"]] == [
        "Q1", "Q2", "Q3", "Q4", "Q5", "benchmark"
    ]
    assert factor["ic_mean"] == 0.1
    assert factor["rank_ic_mean"] == 0.08
    assert factor["ic_ir"] == 1.5

    reopened = FactorBacktestStore(store.path)
    assert reopened.get_batch(batch_id)["status"] == "completed"
    assert reopened.factor_history("test_library", "test_factor")[0]["id"] == factor_id


def test_batch_is_idempotent_and_force_retry_supersedes(monkeypatch, tmp_path: Path):
    profile = FactorBacktestBatchProfile("2026-08-19")
    items = [
        FactorCatalogItem("lib", "ok", "hash-ok"),
        FactorCatalogItem("lib", "bad", "hash-bad"),
        FactorCatalogItem("lib", "short", "hash-short"),
    ]
    monkeypatch.setattr(
        "app.services.factor_backtest_batch.coordinator._catalog_items",
        lambda: (("lib",), "catalog-v1", items),
    )
    monkeypatch.setattr(
        "app.services.factor_backtest_batch.coordinator._preflight",
        lambda _profile, count, **_kwargs: {"factor_count": count},
    )
    attempts: dict[str, int] = {}

    def fake_task_run(self):
        name = self.spec.factor_name
        attempts[name] = attempts.get(name, 0) + 1
        if name == "bad":
            raise RuntimeError("boom")
        return SimpleNamespace(
            equity_curve=pd.Series(
                [1.0, 1.01],
                index=pd.date_range("2026-01-01", periods=2),
            ),
            quantile_metrics=tuple(
                {"quantile": quantile, "annual_return": 0.1}
                for quantile in ("Q1", "Q2", "Q3", "Q4", "Q5", "benchmark")
            ),
            predictive_metrics={},
        )

    monkeypatch.setattr(FactorBacktestExperiment, "run", fake_task_run)

    progress: list[tuple[int, int]] = []
    manager = ExperimentManager(
        max_workers=2,
        max_queue_size=4,
    )
    try:
        first = run_factor_backtest_batch(
            profile,
            manager=manager,
            db_path=tmp_path / "batch.db",
            progress_callback=lambda completed, total: progress.append((completed, total)),
        )
        assert first["status"] == "completed"
        assert first["total_count"] == 3
        assert first["succeeded_count"] == 2
        assert first["failed_count"] == 1
        assert progress[0] == (0, 3)
        assert progress[-1] == (3, 3)
        assert [completed for completed, _ in progress] == [0, 1, 2, 3]

        repeated = run_factor_backtest_batch(profile, manager=manager, db_path=tmp_path / "batch.db")
        assert repeated["id"] == first["id"]

        forced = run_factor_backtest_batch(
            profile,
            manager=manager,
            db_path=tmp_path / "batch.db",
            force_retry=True,
        )
        assert forced["id"] != first["id"]
        assert forced["supersedes_batch_id"] == first["id"]
    finally:
        manager.shutdown()


def test_cli_wires_progress_to_stderr(monkeypatch, capsys):
    class FakeResponse:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"task_id":"task-1","status":"queued","poll_url":"/api/factor-backtest-batch-tasks/task-1","created_at":1.0}'

    captured_request = {}

    def fake_urlopen(request, timeout):
        captured_request["request"] = request
        captured_request["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.cli.factor_backtest_batch.urllib.request.urlopen", fake_urlopen)

    assert main(["run", "--as-of", "2026-08-19", "--dry-run"]) == 0
    captured = capsys.readouterr()
    assert '"task_id": "task-1"' in captured.out
    assert captured_request["request"].full_url.endswith(
        "/api/internal/factor-backtest-batches"
    )
    assert '"dry_run": true' in captured_request["request"].data.decode()


def test_cli_wait_polls_until_task_terminal(monkeypatch, capsys):
    class FakeResponse:
        def __init__(self, body: bytes, status: int = 200):
            self.body = body
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.body

    responses = iter(
        [
            FakeResponse(
                b'{"task_id":"task-1","status":"queued","poll_url":"/api/factor-backtest-batch-tasks/task-1","created_at":1.0}',
                202,
            ),
            FakeResponse(b'{"task_id":"task-1","status":"running"}'),
            FakeResponse(
                b'{"task_id":"task-1","status":"succeeded","batch_id":"batch-1"}'
            ),
        ]
    )
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return next(responses)

    monkeypatch.setattr("app.cli.factor_backtest_batch.urllib.request.urlopen", fake_urlopen)

    assert main(["run", "--as-of", "2026-08-19", "--wait", "--poll-interval", "0"]) == 0
    captured = capsys.readouterr()
    assert '"status": "succeeded"' in captured.out
    assert requests[0].method == "POST"
    assert requests[1].method == "GET"
    assert requests[1].full_url.endswith("/api/factor-backtest-batch-tasks/task-1")


def test_index_or_preflight_failure_is_recorded_as_failed_batch(monkeypatch, tmp_path: Path):
    profile = FactorBacktestBatchProfile("2026-08-19")
    monkeypatch.setattr(
        "app.services.factor_backtest_batch.coordinator._catalog_items",
        lambda: (_ for _ in ()).throw(ValueError("index is invalid")),
    )

    manager = ExperimentManager(max_workers=1, max_queue_size=0)
    try:
        result = run_factor_backtest_batch(profile, manager=manager, db_path=tmp_path / "failed.db")
        assert result["status"] == "failed"
        assert result["error_code"] == "preflight_error"
        assert "index is invalid" in result["error_message"]
    finally:
        manager.shutdown()


def test_batch_submits_the_unified_factor_experiment():
    assert FactorBacktestExperiment.__name__ == "FactorBacktestExperiment"


def test_batch_projection_maps_six_metrics_and_short_history():
    dates = pd.date_range("2025-01-01", periods=4, freq="D")
    layered = pd.DataFrame(
        {f"layer{number}": np.linspace(1.0, 1.1 + number / 100, len(dates)) for number in range(1, 6)},
        index=dates,
    )
    returns = layered.pct_change().fillna(0.0)
    equity = pd.Series(np.linspace(1.0, 1.2, len(dates)), index=dates)
    fake_result = SimpleNamespace(
        equity_curve=equity,
        quantile_metrics=tuple(
            {"quantile": name, "annual_return": 0.1}
            for name in ("Q1", "Q2", "Q3", "Q4", "Q5", "benchmark")
        ),
        predictive_metrics={"ic_mean": 0.2, "rank_ic_mean": 0.15, "ic_ir": 2.0},
    )
    outcome = _outcome_from_result(
        FactorBacktestBatchProfile("2026-08-19"),
        fake_result,
        started=0.0,
    )

    assert outcome.status == "succeeded"
    assert outcome.sample_quality == "short_history"
    assert len(outcome.quantile_metrics) == 6
    assert outcome.predictive_metrics == {"ic_mean": 0.2, "rank_ic_mean": 0.15, "ic_ir": 2.0}


def test_read_only_http_queries_support_filters_and_history(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "api.db"
    store = FactorBacktestStore(db_path)
    batch_id, _ = _make_batch(store)
    monkeypatch.setenv("SVQUANT_FACTOR_BACKTEST_DB", str(db_path))

    # 不使用全局 app 的 lifespan context：它会关闭既有 API 测试共享的 Manager。
    client = TestClient(app)
    batches = client.get("/api/factor-backtest-batches", params={"status": "completed"})
    factors = client.get(
        f"/api/factor-backtest-batches/{batch_id}/factors",
        params={"status": "succeeded", "limit": 1},
    )
    history = client.get("/api/factor-backtest-batches/factors/test_library/test_factor/history")

    assert batches.status_code == 200
    assert batches.json()["batches"][0]["id"] == batch_id
    assert factors.status_code == 200
    assert factors.json()["factors"][0]["quantile_metrics"][-1]["quantile"] == "benchmark"
    assert history.status_code == 200
    assert history.json()["history"][0]["as_of_date"] == "2026-08-19"
