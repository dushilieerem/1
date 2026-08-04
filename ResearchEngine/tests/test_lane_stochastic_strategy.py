"""KD 随机指标策略迁移验收测试。"""

import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _strategy_class():
    asset = StrategyCatalog().load("lane_stochastic_a_share_event")
    namespace = {"__name__": "lane_stochastic_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def test_stochastic_is_slowed_and_remains_in_range():
    strategy = _strategy_class()()
    close = pd.Series(range(1, 41), dtype=float)
    k, d = strategy._stochastic(close + 1, close - 1, close)
    assert k.dropna().between(0, 100).all()
    assert d.dropna().between(0, 100).all()


def test_lane_stochastic_strategy_runs_with_daily_ohlc_panels():
    dates = pd.date_range("2024-01-02", periods=170, freq="B")
    prices = pd.Series([100 + i * .2 + (i % 7 - 3) * .5 for i in range(len(dates))], index=dates)
    panels = {field: pd.DataFrame({"000300.SH": prices, "000001.SZ": prices}, index=dates) for field in ("open", "high", "low", "close")}
    result = EventBacktestEngine(panels).run(_strategy_class()(universe=["000001.SZ"]))
    assert len(result.equity_curve) == len(dates)
    assert result.assumptions["data_visibility"] == "previous_close"
