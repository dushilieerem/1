"""Piotroski F-Score 与股息增长策略迁移测试。"""

import numpy as np
import pandas as pd

from app.services.strategy.event.engine import EventBacktestEngine
from app.services.catalog.strategy_catalog import StrategyCatalog


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=1900, symbols=10):
    dates = pd.bdate_range("2019-01-02", periods=days)
    codes = [f"0000{i:02d}.SZ" for i in range(symbols)]
    close = pd.DataFrame({code: 10 + np.arange(days) * (0.01 + i * 0.001) for i, code in enumerate(codes)}, index=dates)
    panels = {"open": close * 0.999, "high": close * 1.01, "low": close * 0.99, "close": close}
    for field, value in {"pb_mrq": 0.8, "total_mv": 4_000_000_000, "total_assets": 10_000, "total_liabilities": 4_000, "current_assets": 6_000, "current_liabilities": 3_000, "total_shares": 1_000, "operating_revenue_ttm": 8_000, "operating_cost_ttm": 4_000, "net_profit_ttm": 1_000, "net_cashflow_operating_ttm": 1_200, "dividend_yield_ttm": 0.03, "pe_ttm": 12.0}.items():
        panels[field] = pd.DataFrame({code: value + i for i, code in enumerate(codes)}, index=dates)
    dividend = pd.DataFrame(0.0, index=dates, columns=codes)
    for year in range(2019, 2025):
        day = dividend.index[dividend.index.year == year][0]
        dividend.loc[day] = 0.1
    panels["dividend_cash_per_share"] = dividend
    return panels


def test_strategies_are_catalogued_as_event_assets():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    assert assets["piotroski_f_score_a_share_event"]["execution_mode"] == "event"
    assert assets["dividend_growth_a_share_event"]["execution_mode"] == "event"


def test_piotroski_fscore_has_nine_positive_signals():
    strategy = _strategy("piotroski_f_score_a_share_event")()
    values = {"net_profit_ttm": 10, "total_assets": 100, "net_cashflow_operating_ttm": 12, "total_liabilities": 30, "current_assets": 60, "current_liabilities": 20, "total_shares": 100, "operating_revenue_ttm": 100, "operating_cost_ttm": 40}
    previous = {**values, "net_profit_ttm": 5, "total_liabilities": 40, "current_assets": 40, "total_shares": 110, "operating_revenue_ttm": 80, "operating_cost_ttm": 40}
    assert strategy.fscore(values, previous) == 9


def test_both_strategies_run_on_required_point_in_time_panels():
    panels = _panels()
    for strategy_id in ("piotroski_f_score_a_share_event", "dividend_growth_a_share_event"):
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])
