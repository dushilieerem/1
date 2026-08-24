"""风险因子的确定性验证。"""

import numpy as np
import pandas as pd

from app.quantcore.factor.base import Panel, library_factors
from app import FactorLoader


def _panel() -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=130)
    close = pd.DataFrame(
        np.exp(np.linspace(0, 2, 260)).reshape(130, 2),
        index=dates,
        columns=["A", "B"],
    )
    return Panel({"close": close})


def test_risk_indicator_library_registers_first_batch():
    loader = FactorLoader()
    library = loader.load("risk_indicators")

    assert len(library_factors(library)) == 12
    assert "sharpe_ratio_120" in loader.factors
    assert "variance20" in loader.factors


def test_risk_indicator_formulae_match_reference():
    loader = FactorLoader()
    loader.load("risk_indicators")
    panel = _panel()
    returns = panel.close.pct_change()

    variance = loader.factors["variance20"].compute(panel)
    pd.testing.assert_frame_equal(variance, returns.rolling(20).var() * 252)

    sharpe = loader.factors["sharpe_ratio_20"].compute(panel)
    expected_sharpe = (
        returns.rolling(20).mean() * 252 - 0.04
    ) / (returns.rolling(20).std() * np.sqrt(252))
    pd.testing.assert_frame_equal(sharpe, expected_sharpe)


def test_factor_api_lists_risk_indicators():
    from app.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    assert "kurtosis120" in names
    assert "variance120" in names
