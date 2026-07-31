"""Wilder RSI 经典策略的迁移验收测试。"""

from __future__ import annotations

import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _strategy_class():
    asset = StrategyCatalog().load("wilder_rsi_classic_a_share_event")
    namespace = {"__name__": "wilder_rsi_classic_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def test_wilder_rsi_uses_wilder_smoothing_and_stays_in_range():
    strategy = _strategy_class()()
    close = pd.Series([100.0, 98.0, 96.0, 97.0, 95.0, 94.0, 96.0, 98.0, 97.0, 99.0])

    rsi = strategy._rsi(close, period=3)

    assert rsi.dropna().between(0, 100).all()
    assert rsi.iloc[-1] > rsi.iloc[-2]


def test_wilder_rsi_classic_strategy_runs_with_daily_ohlc_panels():
    strategy_class = _strategy_class()
    dates = pd.date_range("2024-01-02", periods=230, freq="B")
    close = pd.Series([100 + index * 0.1 + (index % 9 - 4) * 0.5 for index in range(len(dates))], index=dates)
    panels = {
        field: pd.DataFrame({"000001.SZ": close}, index=dates)
        for field in ("open", "high", "low", "close")
    }

    result = EventBacktestEngine(panels).run(strategy_class(universe=["000001.SZ"]))

    assert len(result.equity_curve) == len(dates)
    assert result.assumptions["data_visibility"] == "previous_close"
