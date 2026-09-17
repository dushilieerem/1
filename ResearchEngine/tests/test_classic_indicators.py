"""迁入经典指标库的确定性公式测试。"""

import pandas as pd
import numpy as np

from app.models.data import Panel
from app.services.factor.base import library_factors
from app.assets.factors import tool
from factor_test_support import BuiltinFactorLoader as FactorLoader
from factor_test_support import builtin_factor_ids


def _panel():
    dates = pd.bdate_range("2024-01-02", periods=80)
    close = pd.DataFrame(np.arange(160, dtype=float).reshape(80, 2) + 10, index=dates, columns=["A", "B"])
    return Panel({"open": close - .5, "high": close + 2, "low": close - 1, "close": close, "volume": close * 100})


def test_classic_indicator_library_is_discoverable():
    library = FactorLoader().load()
    factors = library_factors(library)
    assert {
        "bbi",
        "macd",
        "kdj",
        "rsi",
        "atr",
        "vroc",
        "wvad",
        "channel_position",
        "donchian_width",
        "keltner_width",
    }.issubset(factors)


def test_factor_api_lists_classic_indicators():
    from app.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    ids = builtin_factor_ids()
    assert {
        ids["bbi"],
        ids["macd"],
        ids["kdj"],
        ids["atr"],
        ids["channel_position"],
        ids["keltner_width"],
    }.issubset(names)


def test_classic_indicator_formulae_match_reference():
    loader, panel = FactorLoader(), _panel()
    library = loader.load()
    expected_bbi = sum(panel.close.rolling(n).mean() for n in (3, 6, 12, 24)) / 4
    pd.testing.assert_frame_equal(loader.factors["bbi"].compute(panel), expected_bbi)
    diff = panel.close.ewm(span=12).mean() - panel.close.ewm(span=26).mean()
    pd.testing.assert_frame_equal(
        loader.factors["macd"].compute(panel),
        diff - diff.ewm(span=9).mean(),
    )
    high, low = panel.high.rolling(9).max(), panel.low.rolling(9).min()
    rsv = (panel.close - low) / (high - low) * 100
    k = tool.sma(rsv, 3)
    d = tool.sma(k, 3)
    pd.testing.assert_frame_equal(loader.factors["kdj"].compute(panel), 3 * k - 2 * d)

    middle = panel.close.rolling(20).mean()
    std = panel.close.rolling(20).std()
    upper, lower = middle + 2 * std, middle - 2 * std
    pd.testing.assert_frame_equal(
        loader.factors["channel_position"].compute(panel),
        (panel.close - lower) / (upper - lower + 1e-10),
    )
    donchian_upper = panel.high.rolling(20).max()
    donchian_lower = panel.low.rolling(20).min()
    pd.testing.assert_frame_equal(
        loader.factors["donchian_width"].compute(panel),
        (donchian_upper - donchian_lower) / (panel.close.abs() + 1e-10),
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
    library._panel = panel
    pd.testing.assert_frame_equal(
        library.channel_position(
            channel="keltner", window=20, atr_window=10, multiplier=2.0
        ),
        (panel.close - keltner_lower) / (keltner_upper - keltner_lower + 1e-10),
    )
    pd.testing.assert_frame_equal(
        loader.factors["keltner_width"].compute(panel),
        (keltner_upper - keltner_lower) / (middle.abs() + 1e-10),
    )


def test_classic_indicators_return_panel_shape():
    loader, panel = FactorLoader(), _panel()
    loader.load()
    for name in (
        "bbi", "macd", "kdj", "rsi", "atr", "vroc", "wvad",
        "channel_position", "donchian_width", "keltner_width",
    ):
        assert loader.factors[name].compute(panel).shape == panel.close.shape
