"""情绪因子的确定性验证。"""

import numpy as np
import pandas as pd

from app.quantcore.factor.base import Panel, library_factors
from app import FactorLoader


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


def test_emotion_indicator_library_registers_all_catalogued_factors():
    loader = FactorLoader()
    library = loader.load("emotion_indicators")

    assert len(library_factors(library)) == 36
    assert "atr14" in loader.factors
    assert "wvad" in loader.factors


def test_emotion_indicator_formulae_match_reference():
    loader = FactorLoader()
    loader.load("emotion_indicators")
    panel = _panel()

    vroc12 = loader.factors["vroc12"].compute(panel)
    pd.testing.assert_frame_equal(vroc12, panel.volume.pct_change(12) * 100)

    tvma20 = loader.factors["tvma20"].compute(panel)
    pd.testing.assert_frame_equal(tvma20, panel.amount.rolling(20).mean())

    davol5 = loader.factors["davol5"].compute(panel)
    expected_davol5 = panel.turnover.rolling(5).mean() / panel.turnover.rolling(120).mean()
    pd.testing.assert_frame_equal(davol5, expected_davol5)


def test_emotion_indicators_return_panel_shape():
    loader = FactorLoader()
    loader.load("emotion_indicators")
    panel = _panel()

    for factor in loader.factors.values():
        assert factor.compute(panel).shape == panel.close.shape


def test_factor_api_lists_emotion_indicators():
    from app.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    assert "psy" in names
    assert "vmacd" in names
