"""四个新增经典策略的目录、规则和事件回测验证。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _panels(days=270, symbols=10):
    dates = pd.date_range("2023-01-02", periods=days, freq="B")
    codes = [f"0000{i:02d}.SZ" for i in range(symbols)]
    close = pd.DataFrame({code: 10 + np.arange(days) * (0.03 + i * 0.002) + np.sin(np.arange(days) / 4) for i, code in enumerate(codes)}, index=dates)
    panels = {"open": close * 0.999, "high": close * 1.01, "low": close * 0.99, "close": close}
    panels["amount"] = pd.DataFrame(30_000_000.0, index=dates, columns=codes)
    panels["industry"] = pd.DataFrame({code: f"I{i // 5}" for i, code in enumerate(codes)}, index=dates)
    panels["pe_ratio"] = pd.DataFrame({code: 8 + i for i, code in enumerate(codes)}, index=dates)
    panels["pb_ratio"] = pd.DataFrame({code: 0.8 + i * 0.1 for i, code in enumerate(codes)}, index=dates)
    panels["circulating_market_cap"] = pd.DataFrame({code: 100 + i * 10 for i, code in enumerate(codes)}, index=dates)
    panels["dividend_yield"] = pd.DataFrame({code: 2 + i * 0.2 for i, code in enumerate(codes)}, index=dates)
    return panels


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def test_four_classic_strategies_are_catalogued_as_event_assets():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    for strategy_id in ("jegadeesh_titman_12_1_a_share_event", "fama_french_small_value_a_share_event", "dogs_of_the_dow_low_vol_a_share_event", "elder_triple_screen_a_share_event"):
        assert assets[strategy_id]["execution_mode"] == "event"


def test_momentum_and_value_strategies_build_industry_neutral_candidate_scores():
    panels = _panels()
    for strategy_id in ("jegadeesh_titman_12_1_a_share_event", "fama_french_small_value_a_share_event"):
        cls = _strategy(strategy_id)
        result = EventBacktestEngine(panels).run(cls(max_holdings=4, max_industry_holdings=2))
        assert len(result.equity_curve) == len(panels["close"])


def test_dogs_of_the_dow_uses_january_rebalance_and_triple_screen_runs():
    panels = _panels()
    dog_result = EventBacktestEngine(panels).run(_strategy("dogs_of_the_dow_low_vol_a_share_event")())
    triple_result = EventBacktestEngine(panels).run(_strategy("elder_triple_screen_a_share_event")())
    assert all(order.submitted_at.month == 1 for order in dog_result.orders)
    assert len(triple_result.equity_curve) == len(panels["close"])
