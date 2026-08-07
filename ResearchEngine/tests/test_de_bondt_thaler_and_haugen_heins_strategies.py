"""德邦特—塞勒长期反转与豪根—海因斯低波动异象策略测试。"""

import numpy as np
import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=780, symbols=10):
    dates = pd.bdate_range("2023-01-02", periods=days)
    codes = [f"0000{i:02d}.SZ" for i in range(symbols)]
    close = pd.DataFrame({code: 20 + np.arange(days) * (0.01 + i * 0.001) + np.sin(np.arange(days) / (5 + i)) for i, code in enumerate(codes)}, index=dates)
    panels = {"open": close * 0.999, "high": close * 1.01, "low": close * 0.99, "close": close}
    panels["amount"] = pd.DataFrame(30_000_000.0, index=dates, columns=codes)
    panels["industry"] = pd.DataFrame({code: f"I{i // 5}" for i, code in enumerate(codes)}, index=dates)
    panels["pe_ratio"] = pd.DataFrame({code: 10 + i for i, code in enumerate(codes)}, index=dates)
    panels["pb_ratio"] = pd.DataFrame({code: 0.8 + i * 0.1 for i, code in enumerate(codes)}, index=dates)
    panels["circulating_market_cap"] = pd.DataFrame({code: 100 + i * 10 for i, code in enumerate(codes)}, index=dates)
    return panels


def test_strategies_are_catalogued_as_event_assets():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    for strategy_id in ("de_bondt_thaler_long_term_reversal_a_share_event", "haugen_heins_low_volatility_a_share_event"):
        assert assets[strategy_id]["execution_mode"] == "event"


def test_long_term_reversal_uses_skipped_month_and_recovery_confirmation():
    strategy = _strategy("de_bondt_thaler_long_term_reversal_a_share_event")()
    panels = _panels()
    candidates = strategy._candidates({field: panel.tail(757) for field, panel in panels.items()}, list(panels["close"]))
    assert set(["long_return", "recovery", "volatility", "score"]).issubset(candidates.columns)


def test_both_strategies_run_on_required_point_in_time_panels():
    panels = _panels()
    for strategy_id in ("de_bondt_thaler_long_term_reversal_a_share_event", "haugen_heins_low_volatility_a_share_event"):
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])
