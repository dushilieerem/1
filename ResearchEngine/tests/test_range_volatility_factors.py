"""基于 OHLC 区间的波动率因子确定性验证。"""

import numpy as np
import pandas as pd

from app.models.data import Panel
from factor_test_support import BuiltinFactorLoader as FactorLoader


def _panel() -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=25)
    columns = ["A", "B"]
    close = pd.DataFrame(
        np.arange(10, 60, dtype=float).reshape(25, 2), index=dates, columns=columns
    )
    return Panel({
        "open": close - 0.5,
        "high": close + 2,
        "low": close - 1,
        "close": close,
    })


def test_range_volatility_factor_formulae_match_reference():
    loader = FactorLoader()
    loader.load()
    panel = _panel()

    expected_parkinson = np.sqrt(
        np.log(panel.high / panel.low).pow(2).rolling(20).mean() / (4 * np.log(2))
    )
    pd.testing.assert_frame_equal(loader.factors["parkinson_volatility"].compute(panel), expected_parkinson)

    high_low = np.log(panel.high / panel.low)
    close_open = np.log(panel.close / panel.open)
    expected_garman_klass = np.sqrt(
        (0.5 * high_low.pow(2) - (2 * np.log(2) - 1) * close_open.pow(2)).rolling(20).mean().clip(lower=0)
    )
    pd.testing.assert_frame_equal(
        loader.factors["garman_klass_volatility"].compute(panel), expected_garman_klass
    )

    expected_rogers_satchell = np.sqrt((
        np.log(panel.high / panel.close) * np.log(panel.high / panel.open)
        + np.log(panel.low / panel.close) * np.log(panel.low / panel.open)
    ).rolling(20).mean().clip(lower=0))
    pd.testing.assert_frame_equal(
        loader.factors["rogers_satchell_volatility"].compute(panel), expected_rogers_satchell
    )

    high_low_average = (panel.high - panel.low).ewm(span=10, adjust=False).mean()
    expected_chaikin = (high_low_average / high_low_average.shift(10) - 1) * 100
    pd.testing.assert_frame_equal(loader.factors["chaikin_volatility"].compute(panel), expected_chaikin)


def test_range_volatility_factors_are_discoverable():
    loader = FactorLoader()
    loader.load()

    assert {
        "parkinson_volatility", "garman_klass_volatility",
        "rogers_satchell_volatility", "chaikin_volatility",
    }.issubset(loader.factors)
