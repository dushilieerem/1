"""聚宽兼容技术因子的确定性验证。"""

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


def test_jq_compat_technical_library_registers_first_batch():
    loader = FactorLoader()
    library = loader.load("jq_compat_technical")

    factors = library_factors(library)
    assert len(factors) == 15
    assert set(factors) == {
        "jq_boll_down", "jq_boll_up", "jq_ema5", "jq_emac10", "jq_emac12",
        "jq_emac20", "jq_emac26", "jq_emac120", "jq_mac5", "jq_mac10",
        "jq_mac20", "jq_mac60", "jq_mac120", "jq_macdc", "jq_mfi14",
    }


def test_jq_compat_technical_formulae_match_reference():
    loader = FactorLoader()
    loader.load("jq_compat_technical")
    panel = _panel()

    ema5 = loader.factors["jq_ema5"].compute(panel)
    pd.testing.assert_frame_equal(
        ema5, panel.close.ewm(span=5, adjust=False).mean() / panel.close
    )

    mac20 = loader.factors["jq_mac20"].compute(panel)
    pd.testing.assert_frame_equal(mac20, panel.close.rolling(20).mean() / panel.close)

    boll_up = loader.factors["jq_boll_up"].compute(panel)
    expected_boll_up = (
        panel.close.rolling(20).mean() + 2 * panel.close.rolling(20).std()
    ) / panel.close
    pd.testing.assert_frame_equal(boll_up, expected_boll_up)


def test_jq_compat_technical_factors_return_panel_shape():
    loader = FactorLoader()
    loader.load("jq_compat_technical")
    panel = _panel()

    for factor in loader.factors.values():
        assert factor.compute(panel).shape == panel.close.shape


def test_factor_api_lists_jq_compat_technical_features():
    from researchengine.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    assert "jq_boll_up" in names
    assert "jq_mac120" in names
