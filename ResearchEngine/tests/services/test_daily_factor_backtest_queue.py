"""每日因子业务自有容量为 2 的普通 FIFO 窗口验收。"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

from app.services.daily_factor_backtest import coordinator as daily_module
from app.services.daily_factor_backtest.coordinator import (
    DailyFactorBacktestProfile,
    DailyFactorExperiment,
    FactorCatalogItem,
    FactorOutcome,
    run_factor_batch,
)
from app.services.experiment import Experiment, ExperimentContext
from app.services.experiment.manager import ExperimentManager


class _Runtime:
    def get_context(self, data_dir=None):
        return SimpleNamespace(data_dir=Path("."), data_engine=object(), provider=object())

    def close(self):
        pass


class _InteractiveExperiment(Experiment[str]):
    def __init__(self, started: list[str], lock: threading.Lock) -> None:
        self.started = started
        self.lock = lock

    def run(self, context: ExperimentContext) -> str:
        with self.lock:
            self.started.append("interactive")
        return "interactive"


def test_daily_factor_batch_owns_two_slot_fifo_window(monkeypatch, tmp_path: Path):
    profile = DailyFactorBacktestProfile("2026-08-19")
    items = [
        FactorCatalogItem("library", f"factor_{index}", f"hash-{index}", factor=object())
        for index in range(1, 5)
    ]
    started: list[str] = []
    submitted: list[str] = []
    lock = threading.Lock()
    first_two_started = threading.Event()
    release_first = threading.Event()
    release_second = threading.Event()
    third_started = threading.Event()

    def fake_run(_profile, item, **_kwargs):
        with lock:
            started.append(item.factor_name)
            if {"factor_1", "factor_2"}.issubset(started):
                first_two_started.set()
        if item.factor_name == "factor_1":
            release_first.wait(timeout=3)
        elif item.factor_name == "factor_2":
            release_second.wait(timeout=3)
        elif item.factor_name == "factor_3":
            third_started.set()
        return FactorOutcome(status="succeeded", observation_days=10)

    monkeypatch.setattr(daily_module, "_catalog_items", lambda: (("library",), "v1", items))
    monkeypatch.setattr(
        daily_module,
        "_preflight",
        lambda _profile, count, **_kwargs: {"factor_count": count},
    )
    monkeypatch.setattr(daily_module, "_run_factor_with_retry", fake_run)

    manager = ExperimentManager(max_workers=2, max_queue_size=8, runtime=_Runtime())
    original_submit = manager.submit

    def recording_submit(experiment, *args, **kwargs):
        if isinstance(experiment, DailyFactorExperiment):
            submitted.append(experiment.item.factor_name)
        return original_submit(experiment, *args, **kwargs)

    manager.submit = recording_submit  # type: ignore[method-assign]
    result: list[dict] = []
    errors: list[BaseException] = []

    def run_batch():
        try:
            result.append(
                run_factor_batch(
                    profile,
                    manager=manager,
                    db_path=tmp_path / "batch.db",
                )
            )
        except BaseException as exc:  # pragma: no cover - assertion below reports it
            errors.append(exc)

    worker = threading.Thread(target=run_batch)
    worker.start()
    try:
        assert first_two_started.wait(timeout=3)
        # 批量业务在两个因子尚未结束时不能提交第三个。
        assert submitted == ["factor_1", "factor_2"]

        interactive = manager.submit(_InteractiveExperiment(started, lock), lane="interactive")
        release_first.set()
        assert interactive.result(timeout=3) == "interactive"
        assert third_started.wait(timeout=3)
        assert started.index("interactive") < started.index("factor_3")
        assert submitted[:3] == ["factor_1", "factor_2", "factor_3"]

        release_second.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert not errors
        assert result[0]["status"] == "completed"
        assert submitted == ["factor_1", "factor_2", "factor_3", "factor_4"]
    finally:
        release_first.set()
        release_second.set()
        worker.join(timeout=5)
        manager.shutdown()
