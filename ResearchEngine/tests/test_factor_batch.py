"""FEAT-027 每日全量因子回测：仓库、编排和只读查询测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import ConfigManager
from app.services.experiment.factor import _apply_factor_batch_filters, _predictive_summary
from app.database.factor_backtest_store import (
    FactorBacktestStore,
    default_factor_backtest_db_path,
)
from app.cli.factor_batch import main
from app.services.daily_factor_backtest.coordinator import (
    DailyFactorBacktestProfile,
    FactorCatalogItem,
    FactorOutcome,
    _run_factor_with_retry,
    _run_factor_once,
    run_factor_batch,
)
from app.services.experiment.manager import ExperimentManager


class _StaticRuntime:
    def __init__(self, root: Path):
        self._context = SimpleNamespace(
            data_dir=root,
            data_engine=SimpleNamespace(),
            provider=SimpleNamespace(),
        )

    def get_context(self, data_dir=None):
        return self._context

    def close(self):
        pass


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
        Path("D:/project/SVQuant") / "Factor" / "database" / "factor_backtest.db"
    )


def test_profile_uses_rolling_calendar_years_and_fixed_defaults():
    profile = DailyFactorBacktestProfile("2026-08-19")

    assert profile.window_start == "2016-08-19"
    assert profile.window_end == "2026-08-19"
    assert profile.universe == "CSI_ALL"
    assert profile.benchmark == "CSI300"
    assert profile.portfolio_type == "long_only"
    assert profile.groups == 5
    assert profile.rebalance_days == 1
    assert profile.analysis_level == "core"
    assert profile.filter_limit_up and profile.filter_suspended


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


def test_batch_filters_mask_suspended_and_limit_up_symbols():
    dates = pd.date_range("2026-01-01", periods=2)
    columns = ["A", "B", "C"]
    factor = pd.DataFrame(1.0, index=dates, columns=columns)

    class PanelStub:
        def __init__(self):
            self.fields = {
                "is_suspended": pd.DataFrame(
                    [[False, True, False], [False, False, False]], index=dates, columns=columns
                ),
                "limit_status": pd.DataFrame(
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

    assert pd.isna(filtered.loc[dates[0], "B"])
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
    profile = DailyFactorBacktestProfile("2026-08-19")
    items = [
        FactorCatalogItem("lib", "ok", "hash-ok", factor=object()),
        FactorCatalogItem("lib", "bad", "hash-bad", factor=object()),
        FactorCatalogItem("lib", "short", "hash-short", factor=object()),
    ]
    outcomes = {
        "ok": FactorOutcome(status="succeeded", observation_days=20, sample_quality="complete"),
        "bad": FactorOutcome(status="failed", retry_count=1, error_code="runtime_error", error_message="boom"),
        "short": FactorOutcome(status="succeeded", observation_days=3, sample_quality="short_history"),
    }
    monkeypatch.setattr(
        "app.services.daily_factor_backtest.coordinator._catalog_items",
        lambda: (("lib",), "catalog-v1", items),
    )
    monkeypatch.setattr(
        "app.services.daily_factor_backtest.coordinator._preflight",
        lambda _profile, count, **_kwargs: {"factor_count": count},
    )
    monkeypatch.setattr(
        "app.services.daily_factor_backtest.coordinator._run_factor_with_retry",
        lambda _profile, item, **_kwargs: outcomes[item.factor_name],
    )

    progress: list[tuple[int, int]] = []
    manager = ExperimentManager(
        max_workers=2,
        max_queue_size=4,
        runtime=_StaticRuntime(tmp_path),
    )
    try:
        first = run_factor_batch(
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

        repeated = run_factor_batch(profile, manager=manager, db_path=tmp_path / "batch.db")
        assert repeated["id"] == first["id"]

        forced = run_factor_batch(
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
            return b'{"batch_id":"batch-1","status":"running"}'

    captured_request = {}

    def fake_urlopen(request, timeout):
        captured_request["request"] = request
        captured_request["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.cli.factor_batch.urllib.request.urlopen", fake_urlopen)

    assert main(["run", "--as-of", "2026-08-19", "--dry-run"]) == 0
    captured = capsys.readouterr()
    assert '"batch_id":"batch-1"' in captured.out
    assert captured_request["request"].full_url.endswith(
        "/api/internal/factor-backtests/batches"
    )
    assert '"dry_run": true' in captured_request["request"].data.decode()


def test_index_or_preflight_failure_is_recorded_as_failed_batch(monkeypatch, tmp_path: Path):
    profile = DailyFactorBacktestProfile("2026-08-19")
    monkeypatch.setattr(
        "app.services.daily_factor_backtest.coordinator._catalog_items",
        lambda: (_ for _ in ()).throw(ValueError("index is invalid")),
    )

    manager = ExperimentManager(max_workers=1, max_queue_size=0, runtime=_StaticRuntime(tmp_path))
    try:
        result = run_factor_batch(profile, manager=manager, db_path=tmp_path / "failed.db")
        assert result["status"] == "failed"
        assert result["error_code"] == "preflight_error"
        assert "index is invalid" in result["error_message"]
    finally:
        manager.shutdown()


def test_factor_retry_classifies_incompatible_without_retry_and_runtime_twice(monkeypatch):
    profile = DailyFactorBacktestProfile("2026-08-19")
    item = FactorCatalogItem("lib", "factor", "hash", factor=object())
    calls = {"count": 0}

    def incompatible(_profile, _item):
        calls["count"] += 1
        raise ValueError("参数不兼容")

    monkeypatch.setattr("app.services.daily_factor_backtest.coordinator._run_factor_once", incompatible)
    skipped = _run_factor_with_retry(profile, item)
    assert skipped.status == "skipped"
    assert skipped.retry_count == 0
    assert calls["count"] == 1

    def runtime(_profile, _item):
        calls["count"] += 1
        raise RuntimeError("temporary failure")

    monkeypatch.setattr("app.services.daily_factor_backtest.coordinator._run_factor_once", runtime)
    failed = _run_factor_with_retry(profile, item)
    assert failed.status == "failed"
    assert failed.retry_count == 1
    assert calls["count"] == 3


def test_run_factor_once_maps_six_metrics_and_short_history(monkeypatch):
    dates = pd.date_range("2025-01-01", periods=4, freq="D")
    layered = pd.DataFrame(
        {f"layer{number}": np.linspace(1.0, 1.1 + number / 100, len(dates)) for number in range(1, 6)},
        index=dates,
    )
    returns = layered.pct_change().fillna(0.0)
    equity = pd.Series(np.linspace(1.0, 1.2, len(dates)), index=dates)
    fake_result = SimpleNamespace(
        equity_curve=equity,
        factor_analysis={
            "layered_equity": layered,
            "layered_returns": returns,
            "predictive_summary": {"ic_mean": 0.2, "rank_ic_mean": 0.15, "ic_ir": 2.0},
        },
    )

    class FakeExperiment:
        def __init__(self, **_kwargs):
            pass

        def run(self, _context):
            return fake_result

    monkeypatch.setattr("app.services.daily_factor_backtest.coordinator.FactorExperiment", FakeExperiment)
    monkeypatch.setattr(
        "app.services.daily_factor_backtest.coordinator._load_benchmark_equity",
        lambda _benchmark, index, **_kwargs: pd.Series(1.0, index=index),
    )
    monkeypatch.setattr(
        "app.services.daily_factor_backtest.coordinator._compute_quantile_metrics",
        lambda *_args, **_kwargs: [
            {"quantile": name, "annual_return": 0.1}
            for name in ("Q1", "Q2", "Q3", "Q4", "Q5", "benchmark")
        ],
    )

    outcome = _run_factor_once(
        DailyFactorBacktestProfile("2026-08-19"),
        FactorCatalogItem("lib", "factor", "hash", factor=object()),
        data_context=SimpleNamespace(data_engine=SimpleNamespace()),
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
    batches = client.get("/api/factor-backtests/batches", params={"status": "completed"})
    factors = client.get(
        f"/api/factor-backtests/batches/{batch_id}/factors",
        params={"status": "succeeded", "limit": 1},
    )
    history = client.get("/api/factor-backtests/factors/test_library/test_factor/history")

    assert batches.status_code == 200
    assert batches.json()["batches"][0]["id"] == batch_id
    assert factors.status_code == 200
    assert factors.json()["factors"][0]["quantile_metrics"][-1]["quantile"] == "benchmark"
    assert history.status_code == 200
    assert history.json()["history"][0]["as_of_date"] == "2026-08-19"
