"""技术因子的确定性验证。"""

import numpy as np
import pandas as pd

from quantcore.factor.base import Panel, library_factors
from researchengine import FactorLoader


def _panel() -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=130)
    columns = ["A", "B"]
    close = pd.DataFrame(
        np.arange(1, 261, dtype=float).reshape(130, 2),
        index=dates,
        columns=columns,
    )
    return Panel({
        "high": close + 2,
        "low": close - 1,
        "close": close,
        "volume": close * 100,
    })


def test_technical_indicator_library_registers_first_batch():
    loader = FactorLoader()
    library = loader.load("technical_indicators")

    factors = library_factors(library)
    assert len(factors) == 15
    assert set(factors) == {
        "boll_down", "boll_up", "ema5", "emac10", "emac12",
        "emac20", "emac26", "emac120", "mac5", "mac10",
        "mac20", "mac60", "mac120", "macdc", "mfi14",
    }


def test_technical_indicator_formulae_match_reference():
    loader = FactorLoader()
    loader.load("technical_indicators")
    panel = _panel()

    ema5 = loader.factors["ema5"].compute(panel)
    pd.testing.assert_frame_equal(
        ema5, panel.close.ewm(span=5, adjust=False).mean() / panel.close
    )

    mac20 = loader.factors["mac20"].compute(panel)
    pd.testing.assert_frame_equal(mac20, panel.close.rolling(20).mean() / panel.close)

    boll_up = loader.factors["boll_up"].compute(panel)
    expected_boll_up = (
        panel.close.rolling(20).mean() + 2 * panel.close.rolling(20).std()
    ) / panel.close
    pd.testing.assert_frame_equal(boll_up, expected_boll_up)


def test_technical_indicators_return_panel_shape():
    loader = FactorLoader()
    loader.load("technical_indicators")
    panel = _panel()

    for factor in loader.factors.values():
        assert factor.compute(panel).shape == panel.close.shape


def test_factor_api_lists_technical_indicators():
    from researchengine.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    assert "boll_up" in names
    assert "mac120" in names
