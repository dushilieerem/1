"""Alpha158 / Alpha360 因子库验证。"""

import numpy as np
import pandas as pd

from app.models.data import Panel
from app.services.factor.base import library_factors
from factor_test_support import BuiltinFactorLoader as FactorLoader
from factor_test_support import builtin_factor_ids


def _panel() -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=70)
    columns = ["A", "B"]
    base = pd.DataFrame(
        np.arange(1, 141, dtype=float).reshape(70, 2), index=dates, columns=columns
    )
    return Panel({
        "open": base,
        "high": base + 2,
        "low": base - 1,
        "close": base + 1,
        "volume": base * 10,
        "amount": (base + 0.5) * base * 10,
    })


def test_panel_mask_view_does_not_mutate_the_raw_panel():
    panel = _panel()
    mask = pd.DataFrame(True, index=panel.close.index, columns=panel.close.columns)
    mask.iloc[0, 0] = False

    masked = panel.with_mask(mask)

    assert pd.isna(masked.close.iloc[0, 0])
    assert pd.notna(panel.close.iloc[0, 0])
    pd.testing.assert_frame_equal(panel.with_mask(mask, enabled=False).close, panel.close)


def test_alpha_feature_library_registers_all_standard_features():
    loader = FactorLoader()
    library = loader.load()
    factors = library_factors(library)

    assert len(factors) == 432
    assert {
        "alpha158_kmid",
        "alpha360_close",
        "alpha360_high",
        "alpha360_vwap",
    }.issubset(factors)


def test_alpha_features_match_reference_formulae():
    loader = FactorLoader()
    library = loader.load()
    panel = _panel()

    kmid = loader.factors["alpha158_kmid"].compute(panel)
    expected_kmid = (panel.close - panel.open) / panel.open
    pd.testing.assert_frame_equal(kmid, expected_kmid)

    library._panel = panel
    close5 = library.alpha360_close(window=5)
    pd.testing.assert_frame_equal(close5, panel.close.shift(5) / panel.close)

    vwap0 = library.alpha360_vwap(window=0)
    expected_vwap = (panel.amount / (panel.volume + 1e-12)) / panel.close
    pd.testing.assert_frame_equal(vwap0, expected_vwap)


def test_selected_alpha_features_compute_on_standard_ohlcv_panel():
    loader = FactorLoader()
    loader.load()
    panel = _panel()

    for name in ("alpha158_kmid", "alpha360_close", "alpha360_high", "alpha360_vwap"):
        result = loader.factors[name].compute(panel)
        assert result.shape == panel.close.shape


def test_factor_api_lists_alpha_features():
    from app.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    ids = builtin_factor_ids()
    assert {ids["alpha158_kmid"], ids["alpha360_close"]}.issubset(names)
