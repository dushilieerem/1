"""项目级内置策略库的结构化策略契约测试。"""

from __future__ import annotations

import pandas as pd
import pytest
import numpy as np

from app.quantcore import EventBacktestEngine
from app.repositories.catalogs.strategy_catalog import StrategyCatalog


def test_builtin_strategies_match_their_declared_execution_contract():
    """内置策略必须与策略索引声明的执行模式一致。"""
    namespace = {"__name__": "strategy_contract_test"}
    for asset in (StrategyCatalog().load(item["id"]) for item in StrategyCatalog().list_assets()):
        exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
        strategy_class = namespace[asset.entrypoint]
        if asset.execution_mode == "vectorized":
            assert callable(getattr(strategy_class, "generate_signals", None))
        else:
            assert callable(getattr(strategy_class, "initialize", None))


def test_markowitz_min_variance_strategy_builds_monthly_capped_weights():
    asset = StrategyCatalog().load("markowitz_min_variance")
    namespace = {"__name__": "markowitz_strategy_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    dates = pd.bdate_range("2023-01-02", periods=150)
    rng = np.random.default_rng(7)
    returns = rng.normal(0.001, 0.0001, size=(len(dates), 20))
    close = pd.DataFrame(100.0 * np.exp(np.cumsum(returns, axis=0)), index=dates)

    target = namespace[asset.entrypoint](close).generate_signals().target_weights
    rebalance_rows = target.dropna(how="all")

    assert len(rebalance_rows) == len(dates.to_series().groupby([dates.year, dates.month]).head(1))
    assert (rebalance_rows.iloc[-1] >= 0).all()
    assert rebalance_rows.iloc[-1].sum() == pytest.approx(1.0)
    assert rebalance_rows.iloc[-1].max() <= 0.0800001


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
    panels["amount"] = pd.DataFrame({"000300.SH": 100_000_000, "000001.SZ": 50_000_000}, index=dates)

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


def test_wilder_event_strategy_runs_with_standard_amount_panel():
    asset = StrategyCatalog().load("wilder_adx_rsi_atr_a_share_event")
    namespace = {"__name__": "wilder_event_run_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    dates = pd.date_range("2024-01-02", periods=160, freq="B")
    benchmark = pd.Series(range(100, 260), index=dates, dtype=float)
    stock = pd.Series(range(10, 170), index=dates, dtype=float)
    panels = {
        field: pd.DataFrame({"000300.SH": benchmark, "000001.SZ": stock}, index=dates)
        for field in ("open", "high", "low", "close")
    }
    panels["amount"] = pd.DataFrame(
        {"000300.SH": 100_000_000, "000001.SZ": 50_000_000}, index=dates
    )

    result = EventBacktestEngine(panels).run(namespace[asset.entrypoint]())

    assert len(result.equity_curve) == len(dates)


@pytest.mark.parametrize(
    ("strategy_id", "entrypoint"),
    [
        ("appel_macd_a_share_event", "AppelMacdAShareEventStrategy"),
        ("bollinger_mean_reversion_a_share_event", "BollingerMeanReversionAShareEventStrategy"),
    ],
)
def test_new_a_share_event_strategies_run_with_ohlc_panels(strategy_id, entrypoint):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": f"{strategy_id}_test"}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    dates = pd.date_range("2024-01-02", periods=150, freq="B")
    benchmark = pd.Series(range(100, 250), index=dates, dtype=float)
    stock = pd.Series([20 + index * 0.25 + (index % 6) * 0.5 for index in range(150)], index=dates)
    panels = {
        "open": pd.DataFrame({"000300.SH": benchmark, "000001.SZ": stock}, index=dates),
        "high": pd.DataFrame({"000300.SH": benchmark + 1, "000001.SZ": stock + 1}, index=dates),
        "low": pd.DataFrame({"000300.SH": benchmark - 1, "000001.SZ": stock - 1}, index=dates),
        "close": pd.DataFrame({"000300.SH": benchmark, "000001.SZ": stock}, index=dates),
    }

    result = EventBacktestEngine(panels).run(namespace[entrypoint]())

    assert len(result.equity_curve) == len(dates)
    assert result.assumptions["data_visibility"] == "previous_close"
