"""成交量与资金流因子的确定性验证。"""

import numpy as np
import pandas as pd

from app.quantcore.factor.base import Panel
from app import FactorLoader


def _panel() -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=25)
    columns = ["A", "B"]
    close = pd.DataFrame(
        np.arange(10, 60, dtype=float).reshape(25, 2), index=dates, columns=columns
    )
    volume = pd.DataFrame(
        np.arange(100, 2600, 50, dtype=float).reshape(25, 2), index=dates, columns=columns
    )
    volume.iloc[5::4] = volume.iloc[5::4].shift(1)
    return Panel({"high": close + 2, "low": close - 1, "close": close, "volume": volume})


def test_volume_momentum_factor_formulae_match_reference():
    loader = FactorLoader()
    loader.load("trading_lib")
    panel = _panel()

    expected_pvi = 1000 * (1 + panel.close.pct_change()).where(
        panel.volume > panel.volume.shift(), 1.0
    ).fillna(1.0).cumprod()
    pd.testing.assert_frame_equal(loader.factors["positive_volume_index"].compute(panel), expected_pvi)

    expected_nvi = 1000 * (1 + panel.close.pct_change()).where(
        panel.volume < panel.volume.shift(), 1.0
    ).fillna(1.0).cumprod()
    pd.testing.assert_frame_equal(loader.factors["negative_volume_index"].compute(panel), expected_nvi)

    multiplier = ((panel.close - panel.low) - (panel.high - panel.close)) / (panel.high - panel.low + 1e-10)
    accumulation_distribution = (multiplier * panel.volume).cumsum()
    expected_chaikin = (
        accumulation_distribution.ewm(span=3, adjust=False).mean()
        - accumulation_distribution.ewm(span=10, adjust=False).mean()
    )
    pd.testing.assert_frame_equal(loader.factors["chaikin_oscillator"].compute(panel), expected_chaikin)

    expected_volume_oscillator = (
        panel.volume.rolling(5).mean() / (panel.volume.rolling(20).mean() + 1e-10) - 1
    ) * 100
    pd.testing.assert_frame_equal(loader.factors["volume_oscillator"].compute(panel), expected_volume_oscillator)


def test_volume_momentum_factors_are_discoverable():
    loader = FactorLoader()
    loader.load("trading_lib")

    assert {
        "positive_volume_index", "negative_volume_index", "chaikin_oscillator", "volume_oscillator"
    }.issubset(loader.factors)
