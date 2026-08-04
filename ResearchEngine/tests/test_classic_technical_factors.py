"""经典技术与量价因子的确定性验证。"""

import numpy as np
import pandas as pd

from quantcore.factor.base import Panel
from researchengine import FactorLoader


def _panel() -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=25)
    columns = ["A", "B"]
    close = pd.DataFrame(
        np.arange(10, 60, dtype=float).reshape(25, 2), index=dates, columns=columns
    )
    return Panel({"high": close + 2, "low": close - 1, "close": close, "volume": close * 100})


def test_classic_technical_factor_formulae_match_reference():
    loader = FactorLoader()
    panel = _panel()
    loader.load("technical_lib")
    loader.load("trading_lib")

    typical_price = (panel.high + panel.low + panel.close) / 3
    mean_deviation = typical_price.rolling(20).apply(
        lambda values: np.mean(np.abs(values - values.mean())), raw=True
    )
    expected_cci = (typical_price - typical_price.rolling(20).mean()) / (0.015 * mean_deviation + 1e-10)
    pd.testing.assert_frame_equal(loader.factors["cci"].compute(panel), expected_cci)

    expected_williams_r = -100 * (panel.high.rolling(14).max() - panel.close) / (
        panel.high.rolling(14).max() - panel.low.rolling(14).min() + 1e-10
    )
    pd.testing.assert_frame_equal(loader.factors["williams_r"].compute(panel), expected_williams_r)

    direction = panel.close.diff().gt(0).astype(float) - panel.close.diff().lt(0).astype(float)
    pd.testing.assert_frame_equal(loader.factors["obv"].compute(panel), (direction * panel.volume).cumsum())

    multiplier = ((panel.close - panel.low) - (panel.high - panel.close)) / (panel.high - panel.low + 1e-10)
    expected_cmf = (multiplier * panel.volume).rolling(21).sum() / panel.volume.rolling(21).sum()
    pd.testing.assert_frame_equal(loader.factors["chaikin_money_flow"].compute(panel), expected_cmf)


def test_classic_technical_factors_are_discoverable():
    loader = FactorLoader()
    loader.load("technical_lib")
    loader.load("trading_lib")

    assert {"cci", "williams_r", "obv", "chaikin_money_flow"}.issubset(loader.factors)
