"""ExperimentManager 持有共享行情运行时的测试。"""

from __future__ import annotations

import pandas as pd

from app.services.experiment.manager import ExperimentManager


def _write_market_data(tmp_path):
    panels = tmp_path / "panels"
    panels.mkdir()
    dates = pd.date_range("2024-01-02", periods=3, freq="D")
    pd.DataFrame(
        {"datetime": dates, "A": [10.0, 11.0, 12.0]},
    ).to_parquet(panels / "close.parquet", index=False)


def test_manager_reuses_context_and_refreshes_release(tmp_path):
    _write_market_data(tmp_path)
    manager = ExperimentManager(max_workers=1, max_queue_size=0, data_dir=tmp_path)
    try:
        first = manager.get_data_context()
        second = manager.get_data_context()
        assert first is second
        assert first.data_engine is second.data_engine

        pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-02", periods=3, freq="D"),
                "A": [20.0, 21.0, 22.0],
            },
        ).to_parquet(tmp_path / "panels" / "close.parquet", index=False)

        refreshed = manager.get_data_context()
        assert refreshed is not first
        assert refreshed.release_id != first.release_id
        assert refreshed.data_engine.get_panels(fields=["close"])["close"].iloc[0, 0] == 20.0
    finally:
        manager.shutdown()
