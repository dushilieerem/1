"""DataEngine 持有应用级行情 release 的测试。"""

from __future__ import annotations

import pandas as pd

from app.services.data.engine import DataEngine


def _write_market_data(tmp_path):
    panels = tmp_path / "panels"
    panels.mkdir()
    dates = pd.date_range("2024-01-02", periods=3, freq="D")
    pd.DataFrame(
        {"datetime": dates, "A": [10.0, 11.0, 12.0]},
    ).to_parquet(panels / "close.parquet", index=False)


def test_data_engine_loads_one_fixed_release(tmp_path):
    _write_market_data(tmp_path)
    engine = DataEngine()
    try:
        engine.load_parquet(tmp_path)
        first = engine.get_panels(fields=["close"])["close"]
        assert first.iloc[0, 0] == 10.0

        pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-02", periods=3, freq="D"),
                "A": [20.0, 21.0, 22.0],
            },
        ).to_parquet(tmp_path / "panels" / "close.parquet", index=False)

        # 已加载 release 是进程内固定快照；文件变化不会改变运行中任务数据。
        assert engine.get_panels(fields=["close"])["close"].iloc[0, 0] == 10.0
    finally:
        engine.close()
