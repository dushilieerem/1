"""经典技术与量价因子的确定性验证。"""

import numpy as np
import pandas as pd

from quantcore.factor.base import Panel
from researchengine import FactorLoader


def _panel() -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=60)
    columns = ["A", "B"]
    close = pd.DataFrame(
        np.arange(10, 130, dtype=float).reshape(60, 2), index=dates, columns=columns
    )
    return Panel(
        {
            "open": close - 0.5,
            "high": close + 2,
            "low": close - 1,
            "close": close,
            "volume": close * 100,
        }
    )


def test_classic_technical_factor_formulae_match_reference():
    loader = FactorLoader()
    panel = _panel()
    loader.load("technical_lib")
    loader.load("trading_lib")

    typical_price = (panel.high + panel.low + panel.close) / 3
    mean_deviation = typical_price.rolling(20).apply(
        lambda values: np.mean(np.abs(values - values.mean())), raw=True
    )
    expected_cci = (typical_price - typical_price.rolling(20).mean()) / (0.015 * mean_deviation + 1e-10)
    pd.testing.assert_frame_equal(loader.factors["cci"].compute(panel), expected_cci)

    expected_williams_r = -100 * (panel.high.rolling(14).max() - panel.close) / (
        panel.high.rolling(14).max() - panel.low.rolling(14).min() + 1e-10
    )
    pd.testing.assert_frame_equal(loader.factors["williams_r"].compute(panel), expected_williams_r)

    direction = panel.close.diff().gt(0).astype(float) - panel.close.diff().lt(0).astype(float)
    pd.testing.assert_frame_equal(loader.factors["obv"].compute(panel), (direction * panel.volume).cumsum())

    multiplier = ((panel.close - panel.low) - (panel.high - panel.close)) / (panel.high - panel.low + 1e-10)
    expected_cmf = (multiplier * panel.volume).rolling(21).sum() / panel.volume.rolling(21).sum()
    pd.testing.assert_frame_equal(loader.factors["chaikin_money_flow"].compute(panel), expected_cmf)


def test_trend_and_momentum_factor_formulae_match_reference():
    loader = FactorLoader()
    panel = _panel()
    loader.load("technical_lib")

    expected_aroon_up = 100 * (
        25 - panel.high.rolling(26).apply(lambda values: np.argmax(values[::-1]), raw=True)
    ) / 25
    pd.testing.assert_frame_equal(loader.factors["aroon_up"].compute(panel), expected_aroon_up)

    expected_aroon_down = 100 * (
        25 - panel.low.rolling(26).apply(lambda values: np.argmin(values[::-1]), raw=True)
    ) / 25
    pd.testing.assert_frame_equal(loader.factors["aroon_down"].compute(panel), expected_aroon_down)

    expected_dpo = panel.close.shift(11) - panel.close.rolling(20).mean()
    pd.testing.assert_frame_equal(loader.factors["dpo"].compute(panel), expected_dpo)

    delta = panel.close.diff()
    up_sum = delta.clip(lower=0).rolling(20).sum()
    down_sum = (-delta.clip(upper=0)).rolling(20).sum()
    expected_cmo = 100 * (up_sum - down_sum) / (up_sum + down_sum + 1e-10)
    pd.testing.assert_frame_equal(
        loader.factors["chande_momentum_oscillator"].compute(panel), expected_cmo
    )


def test_oscillator_and_volume_factor_formulae_match_reference():
    loader = FactorLoader()
    panel = _panel()
    loader.load("technical_lib")

    previous_close = panel.close.shift()
    minimum = panel.low.where(panel.low <= previous_close, previous_close)
    maximum = panel.high.where(panel.high >= previous_close, previous_close)
    buying_pressure = panel.close - minimum
    true_range = maximum - minimum

    def average(window):
        return buying_pressure.rolling(window).sum() / (true_range.rolling(window).sum() + 1e-10)

    expected_uo = 100 * (4 * average(7) + 2 * average(14) + average(28)) / 7
    pd.testing.assert_frame_equal(loader.factors["ultimate_oscillator"].compute(panel), expected_uo)

    midpoint = (panel.high + panel.low) / 2
    lowest = midpoint.rolling(10).min()
    highest = midpoint.rolling(10).max()
    price_range = highest - lowest
    normalized = (2 * (midpoint - lowest) / (price_range + 1e-10) - 1).where(
        price_range > 0, 0.0
    ).clip(-0.999999, 0.999999)
    expected_fisher = 0.5 * np.log((1 + normalized) / (1 - normalized))
    pd.testing.assert_frame_equal(loader.factors["fisher_transform"].compute(panel), expected_fisher)

    distance_moved = midpoint.diff()
    box_ratio = (panel.volume / 100000000.0) / (panel.high - panel.low + 1e-10)
    expected_eom = (distance_moved / (box_ratio + 1e-10)).rolling(14).mean()
    pd.testing.assert_frame_equal(loader.factors["ease_of_movement"].compute(panel), expected_eom)

    close_open = panel.close - panel.open
    high_low = panel.high - panel.low
    numerator = (
        close_open + 2 * close_open.shift(1) + 2 * close_open.shift(2) + close_open.shift(3)
    ) / 6
    denominator = (
        high_low + 2 * high_low.shift(1) + 2 * high_low.shift(2) + high_low.shift(3)
    ) / 6
    expected_rvi = numerator.rolling(10).mean() / (denominator.rolling(10).mean() + 1e-10)
    pd.testing.assert_frame_equal(loader.factors["relative_vigor_index"].compute(panel), expected_rvi)

    midpoint = (panel.high + panel.low) / 2
    expected_ao = midpoint.rolling(5).mean() - midpoint.rolling(34).mean()
    pd.testing.assert_frame_equal(loader.factors["awesome_oscillator"].compute(panel), expected_ao)

    expected_bop = (panel.close - panel.open) / (panel.high - panel.low + 1e-10)
    pd.testing.assert_frame_equal(loader.factors["balance_of_power"].compute(panel), expected_bop)

    previous_close = panel.close.shift()
    first = panel.high - panel.low
    second = (panel.high - previous_close).abs()
    third = (panel.low - previous_close).abs()
    true_range = first.where(first >= second, second)
    true_range = true_range.where(true_range >= third, third)
    true_range_sum = true_range.rolling(14).sum()
    price_range = panel.high.rolling(14).max() - panel.low.rolling(14).min()
    ratio = (true_range_sum / (price_range + 1e-10)).clip(lower=1e-10)
    expected_chop = 100 * np.log10(ratio) / np.log10(14)
    pd.testing.assert_frame_equal(loader.factors["choppiness_index"].compute(panel), expected_chop)

    expected_efi = (panel.close.diff() * panel.volume).ewm(span=13, adjust=False).mean()
    pd.testing.assert_frame_equal(loader.factors["elder_force_index"].compute(panel), expected_efi)


def test_directional_and_accumulation_factor_formulae_match_reference():
    loader = FactorLoader()
    panel = _panel()
    loader.load("technical_lib")

    previous_close = panel.close.shift()
    true_range = panel.high - panel.low
    true_range = true_range.where(true_range >= (panel.high - previous_close).abs(), (panel.high - previous_close).abs())
    true_range = true_range.where(true_range >= (panel.low - previous_close).abs(), (panel.low - previous_close).abs())
    up_move = panel.high.diff()
    down_move = -panel.low.diff()
    positive_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    negative_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    positive = 100 * positive_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / (
        true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() + 1e-10
    )
    negative = 100 * negative_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / (
        true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() + 1e-10
    )
    pd.testing.assert_frame_equal(loader.factors["positive_directional_index"].compute(panel), positive)
    pd.testing.assert_frame_equal(loader.factors["negative_directional_index"].compute(panel), negative)

    expected_adx = (
        100 * (positive - negative).abs() / (positive + negative + 1e-10)
    ).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    pd.testing.assert_frame_equal(loader.factors["average_directional_index"].compute(panel), expected_adx)

    multiplier = ((panel.close - panel.low) - (panel.high - panel.close)) / (panel.high - panel.low + 1e-10)
    pd.testing.assert_frame_equal(
        loader.factors["accumulation_distribution"].compute(panel),
        (multiplier * panel.volume).cumsum(),
    )


def test_classic_technical_factors_are_discoverable():
    loader = FactorLoader()
    loader.load("technical_lib")
    loader.load("trading_lib")

    assert {
        "cci", "williams_r", "obv", "chaikin_money_flow", "aroon_up",
        "aroon_down", "dpo", "chande_momentum_oscillator",
        "positive_directional_index", "negative_directional_index",
        "average_directional_index", "accumulation_distribution",
        "ultimate_oscillator", "fisher_transform", "ease_of_movement",
        "relative_vigor_index", "awesome_oscillator", "balance_of_power",
        "choppiness_index", "elder_force_index",
    }.issubset(loader.factors)
