"""凯特纳通道与 Williams %R 策略迁移测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.strategy.event.engine import EventBacktestEngine
from app.services.catalog.strategy_catalog import StrategyCatalog


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels():
    dates = pd.bdate_range("2024-01-02", periods=150)
    close = pd.DataFrame({"000001.SZ": 10 + np.arange(150) * 0.08 + np.sin(np.arange(150) / 3)}, index=dates)
    return {"open": close * 0.999, "high": close * 1.01, "low": close * 0.99, "close": close}


def test_strategies_are_catalogued_as_event_assets():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    assert assets["keltner_channel_breakout_a_share_event"]["execution_mode"] == "event"
    assert assets["williams_percent_r_a_share_event"]["execution_mode"] == "event"


def test_keltner_channels_and_williams_percent_r_match_reference_formulae():
    close = pd.Series(range(10, 50), dtype=float)
    high, low = close + 1, close - 1
    keltner = _strategy("keltner_channel_breakout_a_share_event")()
    middle, upper, lower = keltner._channels(high, low, close)
    assert upper.iloc[-1] > middle.iloc[-1] > lower.iloc[-1]
    williams = _strategy("williams_percent_r_a_share_event")()
    expected = -100 * (high.rolling(14).max() - close) / (high.rolling(14).max() - low.rolling(14).min())
    pd.testing.assert_series_equal(williams._percent_r(high, low, close), expected)


def test_strategies_run_on_daily_ohlc_panels():
    panels = _panels()
    for strategy_id in ("keltner_channel_breakout_a_share_event", "williams_percent_r_a_share_event"):
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])
        assert result.assumptions["data_visibility"] == "previous_close"
