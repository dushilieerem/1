"""Alpha158 / Alpha360 因子库验证。"""

import numpy as np
import pandas as pd

from app.quantcore.factor.base import Panel, library_factors
from app import FactorLoader


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


def test_alpha_feature_library_registers_all_standard_features():
    loader = FactorLoader()
    library = loader.load("alpha_features")
    factors = library_factors(library)

    assert len(factors) == 518
    assert "alpha158_kmid" in factors
    assert "alpha158_vsumd60" in factors
    assert "alpha360_close59" in factors
    assert "alpha360_volume0" in factors


def test_alpha_features_match_reference_formulae():
    loader = FactorLoader()
    loader.load("alpha_features")
    panel = _panel()

    kmid = loader.factors["alpha158_kmid"].compute(panel)
    expected_kmid = (panel.close - panel.open) / panel.open
    pd.testing.assert_frame_equal(kmid, expected_kmid)

    close5 = loader.factors["alpha360_close5"].compute(panel)
    pd.testing.assert_frame_equal(close5, panel.close.shift(5) / panel.close)

    roc5 = loader.factors["alpha158_roc5"].compute(panel)
    pd.testing.assert_frame_equal(roc5, panel.close.shift(5) / panel.close)

    vwap0 = loader.factors["alpha158_vwap0"].compute(panel)
    expected_vwap = (panel.amount / (panel.volume + 1e-12)) / panel.close
    pd.testing.assert_frame_equal(vwap0, expected_vwap)


def test_alpha_features_all_compute_on_standard_ohlcv_panel():
    loader = FactorLoader()
    loader.load("alpha_features")
    panel = _panel()

    for factor in loader.factors.values():
        result = factor.compute(panel)
        assert result.shape == panel.close.shape


def test_factor_api_lists_alpha_features():
    from app.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    assert "alpha158_kmid" in names
    assert "alpha360_close59" in names
