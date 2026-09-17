"""情绪因子的确定性验证。"""

import numpy as np
import pandas as pd

from app.models.data import Panel
from app.services.factor.base import library_factors
from factor_test_support import BuiltinFactorLoader as FactorLoader
from factor_test_support import builtin_factor_ids


def _panel() -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=250)
    close = pd.DataFrame(
        np.arange(1, 501, dtype=float).reshape(250, 2),
        index=dates,
        columns=["A", "B"],
    )
    return Panel({
        "open": close - 0.5,
        "high": close + 2,
        "low": close - 1,
        "close": close,
        "volume": close * 10,
        "amount": close * 100,
        "turnover": close / 100,
    })


def test_builtin_factor_library_exposes_emotion_factor_names():
    loader = FactorLoader()
    library = loader.load()

    assert len(library_factors(library)) == 432
    assert "atr" in loader.factors
    assert "vroc" in loader.factors
    assert "wvad" in loader.factors


def test_emotion_indicator_formulae_match_reference():
    loader = FactorLoader()
    library = loader.load()
    panel = _panel()

    library._panel = panel
    vroc12 = library.vroc(window=12)
    pd.testing.assert_frame_equal(vroc12, panel.volume.pct_change(12) * 100)

    tvma20 = library.tvma(window=20)
    pd.testing.assert_frame_equal(tvma20, panel.amount.rolling(20).mean())

    davol5 = library.davol(window=5)
    expected_davol5 = panel.turnover.rolling(5).mean() / panel.turnover.rolling(120).mean()
    pd.testing.assert_frame_equal(davol5, expected_davol5)


def test_emotion_indicators_return_panel_shape():
    loader = FactorLoader()
    loader.load()
    panel = _panel()

    for name in ("atr", "vroc", "tvma", "davol", "psy", "wvad", "vmacd"):
        assert loader.factors[name].compute(panel).shape == panel.close.shape


def test_factor_api_lists_emotion_indicators():
    from app.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    ids = builtin_factor_ids()
    assert {ids["psy"], ids["vmacd"]}.issubset(names)
