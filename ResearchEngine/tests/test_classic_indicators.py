"""迁入经典指标库的确定性公式测试。"""

import pandas as pd
import numpy as np

from quantcore.factor.base import Panel, library_factors
from researchengine import FactorLoader


def _panel():
    dates = pd.bdate_range("2024-01-02", periods=80)
    close = pd.DataFrame(np.arange(160, dtype=float).reshape(80, 2) + 10, index=dates, columns=["A", "B"])
    return Panel({"open": close - .5, "high": close + 2, "low": close - 1, "close": close, "volume": close * 100})


def test_classic_indicator_library_is_discoverable():
    library = FactorLoader().load("classic_indicators")
    factors = library_factors(library)
    assert {
        "bbi",
        "macd",
        "kdj",
        "rsi",
        "atr",
        "vroc",
        "wad",
        "cvlt",
        "donchian_position",
        "donchian_width",
        "keltner_position",
        "keltner_width",
    }.issubset(factors)


def test_factor_api_lists_classic_indicators():
    from researchengine.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    assert {
        "bbi",
        "macd",
        "kdj",
        "atr",
        "donchian_position",
        "keltner_width",
    }.issubset(names)


def test_classic_indicator_formulae_match_reference():
    loader, panel = FactorLoader(), _panel()
    loader.load("classic_indicators")
    expected_bbi = sum(panel.close.rolling(n).mean() for n in (3, 6, 12, 24)) / 4
    pd.testing.assert_frame_equal(loader.factors["bbi"].compute(panel), expected_bbi)
    diff = panel.close.ewm(span=12, adjust=False).mean() - panel.close.ewm(span=26, adjust=False).mean()
    pd.testing.assert_frame_equal(loader.factors["macd"].compute(panel), 2 * (diff - diff.ewm(span=9, adjust=False).mean()))
    high, low = panel.high.rolling(9).max(), panel.low.rolling(9).min()
    rsv = (panel.close - low) / (high - low) * 100
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    pd.testing.assert_frame_equal(loader.factors["kdj"].compute(panel), 3 * k - 2 * d)

    upper = panel.high.rolling(20).max()
    lower = panel.low.rolling(20).min()
    pd.testing.assert_frame_equal(
        loader.factors["donchian_position"].compute(panel),
        (panel.close - lower) / (upper - lower + 1e-10),
    )
    pd.testing.assert_frame_equal(
        loader.factors["donchian_width"].compute(panel),
        (upper - lower) / (panel.close.abs() + 1e-10),
    )

    previous_close = panel.close.shift()
    true_range = panel.high - panel.low
    true_range = true_range.where(
        true_range >= (panel.high - previous_close).abs(),
        (panel.high - previous_close).abs(),
    )
    true_range = true_range.where(
        true_range >= (panel.low - previous_close).abs(),
        (panel.low - previous_close).abs(),
    )
    middle = panel.close.ewm(span=20, adjust=False).mean()
    offset = 2.0 * true_range.rolling(10).mean()
    keltner_upper, keltner_lower = middle + offset, middle - offset
    pd.testing.assert_frame_equal(
        loader.factors["keltner_position"].compute(panel),
        (panel.close - keltner_lower) / (keltner_upper - keltner_lower + 1e-10),
    )
    pd.testing.assert_frame_equal(
        loader.factors["keltner_width"].compute(panel),
        (keltner_upper - keltner_lower) / (middle.abs() + 1e-10),
    )


def test_classic_indicators_return_panel_shape():
    loader, panel = FactorLoader(), _panel()
    loader.load("classic_indicators")
    for factor in loader.factors.values():
        assert factor.compute(panel).shape == panel.close.shape
