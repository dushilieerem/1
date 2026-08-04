"""一目均衡表策略迁移验收测试。"""

import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _strategy_class():
    asset = StrategyCatalog().load("hosoda_ichimoku_a_share_event")
    namespace = {"__name__": "hosoda_ichimoku_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def test_ichimoku_cloud_uses_shifted_past_bars():
    strategy = _strategy_class()()
    values = pd.Series(range(1, 80), dtype=float)
    state = strategy._state(values + 1, values - 1, values)
    assert state is not None
    assert state["cloud_b"] == (values.iloc[-78:-26].max() + (values - 1).iloc[-78:-26].min() + 1) / 2


def test_hosoda_ichimoku_strategy_runs_with_daily_ohlc_panels():
    dates = pd.date_range("2024-01-02", periods=130, freq="B")
    prices = pd.Series(range(100, 230), index=dates, dtype=float)
    panels = {field: pd.DataFrame({"000300.SH": prices, "000001.SZ": prices}, index=dates) for field in ("open", "high", "low", "close")}
    result = EventBacktestEngine(panels).run(_strategy_class()(universe=["000001.SZ"]))
    assert len(result.equity_curve) == len(dates)
    assert result.assumptions["data_visibility"] == "previous_close"
