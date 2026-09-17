"""贵州茅台日频海龟策略的策略资产测试。"""

from __future__ import annotations

import pandas as pd

from app.services.strategy.event.engine import EventBacktestEngine
from app.services.catalog.strategy_catalog import StrategyCatalog


def test_turtle_trading_maotai_strategy_adds_up_to_four_units_then_exits():
    asset = StrategyCatalog().load("turtle_trading_maotai")
    namespace = {"__name__": "turtle_trading_maotai_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    dates = pd.bdate_range("2024-01-02", periods=70)
    close = pd.Series([10.0] * 25 + [10.6 + 0.6 * index for index in range(25)] + [8.0] * 20, index=dates)
    panels = {
        "open": pd.DataFrame({"600519.SH": close}, index=dates),
        "high": pd.DataFrame({"600519.SH": close + 0.4}, index=dates),
        "low": pd.DataFrame({"600519.SH": close - 0.4}, index=dates),
        "close": pd.DataFrame({"600519.SH": close}, index=dates),
    }

    result = EventBacktestEngine(panels).run(namespace[asset.entrypoint]())

    buy_fills = [fill for fill in result.fills if fill.side == "buy"]
    sell_fills = [fill for fill in result.fills if fill.side == "sell"]
    assert len(buy_fills) == 4
    assert sell_fills
    assert result.position_snapshots[-1].positions == {"600519.SH": 0}
