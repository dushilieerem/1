"""CMO、Fisher、EOM 与 VPT 策略迁移验收测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.strategy.event.engine import EventBacktestEngine
from app.services.catalog.strategy_catalog import StrategyCatalog


STRATEGIES = {
    "chande_momentum_oscillator_a_share_event": "ChandeMomentumOscillatorAShareEventStrategy",
    "fisher_transform_a_share_event": "FisherTransformAShareEventStrategy",
    "ease_of_movement_a_share_event": "EaseOfMovementAShareEventStrategy",
    "volume_price_trend_a_share_event": "VolumePriceTrendAShareEventStrategy",
}


def _strategy(strategy_id):
    asset = StrategyCatalog().load(strategy_id)
    namespace = {"__name__": strategy_id}
    exec(compile(asset.source_code, asset.entrypoint, "exec"), namespace)
    return namespace[asset.entrypoint]


def _panels(days=220, symbols=12):
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


def test_cmo_matches_normalized_up_down_momentum_formula():
    strategy_class = _strategy("chande_momentum_oscillator_a_share_event")
    close = pd.Series(np.linspace(10.0, 30.0, 40) + np.sin(np.arange(40)), dtype=float)
    actual = strategy_class._cmo(close, 20)

    delta = close.diff()
    up_sum = delta.clip(lower=0).rolling(20).sum()
    down_sum = (-delta.clip(upper=0)).rolling(20).sum()
    expected = 100.0 * (up_sum - down_sum) / (up_sum + down_sum + 1e-10)
    assert actual.iloc[-1] == pytest.approx(expected.iloc[-1])


def test_fisher_matches_rolling_midpoint_normalization_formula():
    strategy_class = _strategy("fisher_transform_a_share_event")
    close = pd.Series(np.linspace(10.0, 30.0, 40) + np.sin(np.arange(40)), dtype=float)
    high, low = close + 1.0, close - 1.0
    actual = strategy_class._fisher(high, low, 10)

    midpoint = (high + low) / 2.0
    lowest = midpoint.rolling(10).min()
    highest = midpoint.rolling(10).max()
    price_range = highest - lowest
    normalized = (
        2.0 * (midpoint - lowest) / (price_range + 1e-10) - 1.0
    ).where(price_range > 0, 0.0).clip(-0.999999, 0.999999)
    expected = 0.5 * np.log((1.0 + normalized) / (1.0 - normalized))
    assert actual.iloc[-1] == pytest.approx(expected.iloc[-1])


def test_eom_and_vpt_match_reference_formulae():
    eom_class = _strategy("ease_of_movement_a_share_event")
    close = pd.Series(np.linspace(10.0, 30.0, 40) + np.sin(np.arange(40)), dtype=float)
    high, low = close + 1.0, close - 1.0
    volume = pd.Series(np.linspace(1_000_000.0, 2_000_000.0, 40))
    actual_eom = eom_class._eom(high, low, volume, 14, 100_000_000.0)

    midpoint = (high + low) / 2.0
    distance_moved = midpoint.diff()
    box_ratio = (volume / 100_000_000.0) / (high - low + 1e-10)
    expected_eom = (distance_moved / (box_ratio + 1e-10)).rolling(14).mean()
    assert actual_eom.iloc[-1] == pytest.approx(expected_eom.iloc[-1])

    vpt_class = _strategy("volume_price_trend_a_share_event")
    actual_vpt = vpt_class._vpt(close, volume)
    expected_vpt = (close.pct_change().fillna(0.0) * volume).cumsum()
    pd.testing.assert_series_equal(actual_vpt, expected_vpt)


def test_event_strategies_run_with_required_ohlc_and_ohlcv_panels():
    panels = _panels()
    for strategy_id in STRATEGIES:
        result = EventBacktestEngine(panels).run(_strategy(strategy_id)())
        assert len(result.equity_curve) == len(panels["close"])
        assert result.assumptions["data_visibility"] == "previous_close"


@pytest.mark.parametrize(
    "strategy_id",
    ["ease_of_movement_a_share_event", "volume_price_trend_a_share_event"],
)
def test_volume_strategies_reject_panels_without_volume(strategy_id):
    panels = _panels()
    panels.pop("volume")
    with pytest.raises(ValueError, match="策略缺少数据字段"):
        EventBacktestEngine(panels).run(_strategy(strategy_id)())
