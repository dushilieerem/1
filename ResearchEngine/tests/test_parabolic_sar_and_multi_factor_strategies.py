"""抛物线 SAR 与 Fama-French 多因子策略迁移测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=280, symbols=12):
    dates = pd.bdate_range("2023-01-02", periods=days)
    codes = [f"0000{i:02d}.SZ" for i in range(symbols)]
    close = pd.DataFrame({code: 10 + np.arange(days) * (0.03 + i * 0.002) + np.sin(np.arange(days) / 6) for i, code in enumerate(codes)}, index=dates)
    panels = {"open": close * 0.999, "high": close * 1.01, "low": close * 0.99, "close": close}
    panels["market_cap"] = pd.DataFrame({code: 3_100_000_000 + i * 300_000_000 for i, code in enumerate(codes)}, index=dates)
    panels["pb_ratio"] = pd.DataFrame({code: 0.8 + i * 0.1 for i, code in enumerate(codes)}, index=dates)
    return panels


def test_strategies_are_catalogued_as_event_assets():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    assert assets["wilder_parabolic_sar_a_share_event"]["execution_mode"] == "event"
    assert assets["fama_french_carhart_multi_factor_a_share_event"]["execution_mode"] == "event"


def test_parabolic_sar_reverses_after_breaking_the_trailing_stop():
    strategy = _strategy("wilder_parabolic_sar_a_share_event")()
    high = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 15], dtype=float)
    low = pd.Series([9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 10], dtype=float)
    sar, trend = strategy._sar(high, low, (high + low) / 2)
    assert trend.iloc[-2] == 1
    assert trend.iloc[-1] == -1
    assert sar.iloc[-1] == high.iloc[-2]


def test_strategies_run_on_required_point_in_time_panels():
    panels = _panels()
    sar_result = EventBacktestEngine(panels).run(_strategy("wilder_parabolic_sar_a_share_event")())
    factor_result = EventBacktestEngine(panels).run(_strategy("fama_french_carhart_multi_factor_a_share_event")())
    assert len(sar_result.equity_curve) == len(panels["close"])
    assert len(factor_result.equity_curve) == len(panels["close"])
