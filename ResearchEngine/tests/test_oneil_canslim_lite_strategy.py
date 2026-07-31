"""CANSLIM Lite 无基本面数据迁移验收测试。"""

from __future__ import annotations

import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _strategy_class():
    asset = StrategyCatalog().load("oneil_canslim_lite_a_share_event")
    namespace = {"__name__": "oneil_canslim_lite_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def test_canslim_lite_base_breakout_uses_only_month_end_close():
    strategy = _strategy_class()()
    dates = pd.date_range("2024-01-01", "2024-04-30", freq="B")
    close = pd.Series(100.0, index=dates)
    close.loc["2024-02-29"] = 90.0
    close.loc["2024-03-29"] = 80.0
    close.loc["2024-04-30"] = 110.0

    assert strategy._base_breakout(close)


def test_canslim_lite_strategy_runs_with_close_and_benchmark_only():
    strategy_class = _strategy_class()
    dates = pd.date_range("2023-01-02", periods=300, freq="B")
    benchmark = pd.Series(range(100, 400), index=dates, dtype=float)
    stock = pd.Series(range(20, 320), index=dates, dtype=float)
    panels = {
        field: pd.DataFrame({"000300.SH": benchmark, "000001.SZ": stock}, index=dates)
        for field in ("open", "high", "low", "close")
    }

    result = EventBacktestEngine(panels).run(strategy_class(universe=["000001.SZ"]))

    assert len(result.equity_curve) == len(dates)
    assert result.assumptions["data_visibility"] == "previous_close"
