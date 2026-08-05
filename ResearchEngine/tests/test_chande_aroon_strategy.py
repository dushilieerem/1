"""Aroon 趋势策略迁移验收测试。"""

import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _strategy_class():
    asset = StrategyCatalog().load("chande_aroon_a_share_event")
    namespace = {"__name__": "chande_aroon_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def test_aroon_uses_most_recent_extreme_in_26_bar_window():
    strategy = _strategy_class()()
    high = pd.Series(list(range(1, 26)) + [10], dtype=float)
    low = pd.Series(list(range(26, 1, -1)) + [1], dtype=float)
    up, down = strategy._aroon(high, low)
    assert up == 96.0
    assert down == 100.0


def test_chande_aroon_strategy_runs_with_daily_ohlc_panels():
    dates = pd.bdate_range("2024-01-02", periods=170)
    benchmark = pd.Series(range(100, 270), index=dates, dtype=float)
    stock = pd.Series([20 + index * 0.25 + (index % 6) * 0.5 for index in range(len(dates))], index=dates)
    panels = {
        field: pd.DataFrame({"000300.SH": benchmark, "000001.SZ": stock}, index=dates)
        for field in ("open", "high", "low", "close")
    }
    result = EventBacktestEngine(panels).run(_strategy_class()(universe=["000001.SZ"]))
    assert len(result.equity_curve) == len(dates)
    assert result.assumptions["data_visibility"] == "previous_close"
