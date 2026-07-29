"""项目级内置策略库的结构化策略契约测试。"""

from __future__ import annotations

import pandas as pd

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


def test_builtin_strategies_match_their_declared_execution_contract():
    """内置策略必须与策略索引声明的执行模式一致。"""
    namespace = {"__name__": "strategy_contract_test"}
    from quantcore import FactorPortfolioStrategy

    for asset in (StrategyCatalog().load(item["id"]) for item in StrategyCatalog().list_assets()):
        exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
        strategy_class = namespace[asset.entrypoint]
        if asset.execution_mode == "vectorized":
            assert issubclass(strategy_class, FactorPortfolioStrategy)
        else:
            assert callable(getattr(strategy_class, "initialize", None))


def test_donchian_a_share_event_strategy_runs_with_event_engine():
    asset = StrategyCatalog().load("donchian_a_share_event")
    namespace = {"__name__": "donchian_event_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    dates = pd.date_range("2024-01-02", periods=125, freq="B")
    benchmark = pd.Series(range(100, 225), index=dates, dtype=float)
    stock = pd.Series(range(10, 135), index=dates, dtype=float)
    panels = {
        field: pd.DataFrame({"000300.SH": benchmark, "000001.SZ": stock}, index=dates)
        for field in ("open", "high", "low", "close")
    }
    panels["money"] = pd.DataFrame({"000300.SH": 100_000_000, "000001.SZ": 50_000_000}, index=dates)

    result = EventBacktestEngine(panels).run(namespace[asset.entrypoint]())

    assert result.fills
    assert result.fills[0].symbol == "000001.SZ"


def test_wilder_event_strategy_calculates_complete_indicator_set():
    asset = StrategyCatalog().load("wilder_adx_rsi_atr_a_share_event")
    namespace = {"__name__": "wilder_event_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    dates = pd.date_range("2024-01-02", periods=100, freq="B")
    close = pd.Series([100 + index * 0.2 + (index % 7) * 0.4 for index in range(100)], index=dates)
    strategy = namespace[asset.entrypoint]()

    indicators = strategy._indicators(close + 1, close - 1, close)

    assert {"atr", "plus_di", "minus_di", "adx", "rsi"}.issubset(indicators)
    assert indicators.iloc[-1].notna().all()
