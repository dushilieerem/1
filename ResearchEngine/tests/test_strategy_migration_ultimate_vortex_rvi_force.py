"""Ultimate Oscillator、Vortex、RVI 与 Force Index 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantcore import EventBacktestEngine
from researchengine.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "ultimate_oscillator_a_share_event": "UltimateOscillatorAShareEventStrategy",
    "vortex_indicator_a_share_event": "VortexIndicatorAShareEventStrategy",
    "relative_vigor_index_a_share_event": "RelativeVigorIndexAShareEventStrategy",
    "elder_force_index_a_share_event": "ElderForceIndexAShareEventStrategy",
}


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=260, symbols=12):
    dates = pd.bdate_range("2023-01-02", periods=days)
    codes = [f"0000{i:02d}.SZ" for i in range(symbols)]
    steps = np.arange(days, dtype=float)
    close = pd.DataFrame(
        {
            code: 20 + steps * (0.02 + index * 0.001) + np.sin(steps / (4 + index))
            for index, code in enumerate(codes)
        },
        index=dates,
    )
    return {
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": pd.DataFrame(
            {
                code: 1_000_000 + (steps % 10) * 10_000 + index * 1_000
                for index, code in enumerate(codes)
            },
            index=dates,
        ),
    }


def test_four_strategies_are_catalogued_as_event_assets():
    assets = {item["id"]: item for item in StrategyCatalog().list_assets()}
    for strategy_id in STRATEGIES:
        assert assets[strategy_id]["execution_mode"] == "event"


def test_ultimate_oscillator_matches_weighted_multi_period_formula():
    strategy_class = _strategy("ultimate_oscillator_a_share_event")
    close = pd.Series(np.linspace(10.0, 30.0, 40))
    high, low = close + 1.0, close - 1.0
    actual = strategy_class._ultimate_oscillator(high, low, close, 7, 14, 28)

    previous_close = close.shift()
    minimum = low.where(low <= previous_close, previous_close)
    maximum = high.where(high >= previous_close, previous_close)
    buying_pressure = close - minimum
    true_range = maximum - minimum

    def average(window):
        return buying_pressure.rolling(window).sum() / (true_range.rolling(window).sum() + 1e-10)

    expected = 100.0 * (4.0 * average(7) + 2.0 * average(14) + average(28)) / 7.0
    assert actual.iloc[-1] == pytest.approx(expected.iloc[-1])


def test_vortex_matches_positive_and_negative_movement_formula():
    strategy_class = _strategy("vortex_indicator_a_share_event")
    close = pd.Series([10.0 + index * 0.3 + (index % 4) * 0.2 for index in range(35)])
    high, low = close + 1.0, close - 1.0
    actual_plus, actual_minus = strategy_class._vortex(high, low, close, 14)

    previous_close = close.shift()
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    denominator = true_range.rolling(14).sum().replace(0, float("nan"))
    expected_plus = (high - low.shift()).abs().rolling(14).sum() / denominator
    expected_minus = (low - high.shift()).abs().rolling(14).sum() / denominator
    assert actual_plus.iloc[-1] == pytest.approx(expected_plus.iloc[-1])
    assert actual_minus.iloc[-1] == pytest.approx(expected_minus.iloc[-1])


def test_rvi_and_force_index_match_reference_formulas():
    rvi_class = _strategy("relative_vigor_index_a_share_event")
    close = pd.Series(np.linspace(10.0, 30.0, 40))
    open_price, high, low = close - 0.2, close + 1.0, close - 1.0
    actual_rvi = rvi_class._rvi(open_price, high, low, close, 10)

    close_open = close - open_price
    high_low = high - low
    numerator = (close_open + 2 * close_open.shift(1) + 2 * close_open.shift(2) + close_open.shift(3)) / 6.0
    denominator = (high_low + 2 * high_low.shift(1) + 2 * high_low.shift(2) + high_low.shift(3)) / 6.0
    expected_rvi = numerator.rolling(10).mean() / (denominator.rolling(10).mean() + 1e-10)
    assert actual_rvi.iloc[-1] == pytest.approx(expected_rvi.iloc[-1])

    force_class = _strategy("elder_force_index_a_share_event")
    volume = pd.Series(np.linspace(1_000_000.0, 2_000_000.0, 40))
    actual_force = force_class._force_index(close, volume, 13)
    expected_force = (close.diff() * volume).ewm(span=13, adjust=False, min_periods=13).mean()
    assert actual_force.iloc[-1] == pytest.approx(expected_force.iloc[-1])


def test_event_strategies_run_with_required_ohlc_and_ohlcv_panels():
    panels = _panels()
    for strategy_id in STRATEGIES:
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])
        assert result.assumptions["data_visibility"] == "previous_close"


def test_force_index_rejects_panels_without_volume():
    panels = _panels()
    panels.pop("volume")
    with pytest.raises(ValueError, match="强力指数策略缺少数据字段"):
        EventBacktestEngine(panels).run(_strategy("elder_force_index_a_share_event")())
