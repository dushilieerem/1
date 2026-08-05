"""聂夫低市盈率与戴维斯双击策略迁移测试。"""

from __future__ import annotations

import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _panels(days=30):
    dates = pd.date_range("2024-01-02", periods=days, freq="B")
    symbols = ["000001.SZ", "000002.SZ"]
    close = pd.DataFrame({symbol: 100 + pd.Series(range(days), index=dates) for symbol in symbols})
    panels = {field: close.copy() for field in ("open", "high", "low", "close")}
    panels["pe_ratio"] = pd.DataFrame({"000001.SZ": 10.0, "000002.SZ": 30.0}, index=dates)
    panels["dividend_yield"] = pd.DataFrame({"000001.SZ": 3.0, "000002.SZ": 3.0}, index=dates)
    panels["inc_net_profit_year_on_year"] = pd.DataFrame({"000001.SZ": 20.0, "000002.SZ": 20.0}, index=dates)
    panels["roe"] = pd.DataFrame({"000001.SZ": 15.0, "000002.SZ": 15.0}, index=dates)
    return panels


def test_value_strategies_are_catalogued_as_event_assets():
    catalog = StrategyCatalog()
    assets = {item["id"]: item for item in catalog.list_assets()}
    assert assets["neff_low_pe_a_share_event"]["execution_mode"] == "event"
    assert assets["davis_double_play_a_share_event"]["execution_mode"] == "event"


def test_neff_strategy_filters_low_pe_and_runs():
    asset = StrategyCatalog().load("neff_low_pe_a_share_event")
    namespace = {}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    result = EventBacktestEngine(_panels()).run(namespace[asset.entrypoint]())
    assert len(result.equity_curve) == 30
    assert any(fill.symbol == "000001.SZ" for fill in result.fills)
    assert all(fill.symbol != "000002.SZ" for fill in result.fills)


def test_davis_strategy_runs_with_historical_pe_panel():
    asset = StrategyCatalog().load("davis_double_play_a_share_event")
    namespace = {}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    result = EventBacktestEngine(_panels(40)).run(namespace[asset.entrypoint]())
    assert len(result.equity_curve) == 40
