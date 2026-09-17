"""贵州茅台 13/26 日双均线策略的策略资产测试。"""

from __future__ import annotations

import pandas as pd

from app.services.catalog.strategy_catalog import StrategyCatalog


def test_ma_13_26_maotai_strategy_targets_only_maotai():
    asset = StrategyCatalog().load("ma_13_26_maotai")
    namespace = {"__name__": "ma_13_26_maotai_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    dates = pd.bdate_range("2024-01-02", periods=70)
    close = pd.DataFrame(
        {
            "600519.SH": list(range(100, 140)) + list(range(139, 109, -1)),
            "000001.SZ": range(70),
        },
        index=dates,
        dtype=float,
    )

    target = namespace[asset.entrypoint](close).generate_signals()

    assert (target["000001.SZ"] == 0.0).all()
    assert (target.iloc[:25]["600519.SH"] == 0.0).all()
    assert target.iloc[25]["600519.SH"] == 1.0
    assert target.iloc[-1]["600519.SH"] == 0.0
