"""技术因子的确定性验证。"""

import numpy as np
import pandas as pd

from app.models.data import Panel
from app.services.factor.base import library_factors
from factor_test_support import BuiltinFactorLoader as FactorLoader
from factor_test_support import builtin_factor_ids


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
    library = loader.load()

    factors = library_factors(library)
    assert len(factors) == 432
    assert {"boll_down", "boll_up", "expma", "simple_moving_average"}.issubset(factors)


def test_technical_indicator_formulae_match_reference():
    loader = FactorLoader()
    loader.load()
    panel = _panel()

    library = loader.load()
    expma5 = loader.factors["expma"].compute(panel)
    pd.testing.assert_frame_equal(
        expma5, panel.close.ewm(span=5, adjust=False).mean()
    )

    library._panel = panel
    sma20 = library.simple_moving_average(window=20)
    pd.testing.assert_frame_equal(sma20, panel.close.rolling(20).mean())

    boll_up = loader.factors["boll_up"].compute(panel)
    expected_boll_up = (
        panel.close.rolling(20).mean() + 2 * panel.close.rolling(20).std()
    ) / panel.close
    pd.testing.assert_frame_equal(boll_up, expected_boll_up)


def test_technical_indicators_return_panel_shape():
    loader = FactorLoader()
    loader.load()
    panel = _panel()

    for name in ("boll_down", "boll_up", "expma", "simple_moving_average"):
        assert loader.factors[name].compute(panel).shape == panel.close.shape


def test_factor_api_lists_technical_indicators():
    from app.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    ids = builtin_factor_ids()
    assert {ids["boll_up"], ids["expma"]}.issubset(names)
