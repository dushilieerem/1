"""经典技术与量价因子的确定性验证。"""

import numpy as np
import pandas as pd

from quantcore.factor.base import Panel
from researchengine import FactorLoader


def _panel() -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=30)
    columns = ["A", "B"]
    close = pd.DataFrame(
        np.arange(10, 70, dtype=float).reshape(30, 2), index=dates, columns=columns
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


def test_trend_and_momentum_factor_formulae_match_reference():
    loader = FactorLoader()
    panel = _panel()
    loader.load("technical_lib")

    expected_aroon_up = 100 * (
        25 - panel.high.rolling(26).apply(lambda values: np.argmax(values[::-1]), raw=True)
    ) / 25
    pd.testing.assert_frame_equal(loader.factors["aroon_up"].compute(panel), expected_aroon_up)

    expected_aroon_down = 100 * (
        25 - panel.low.rolling(26).apply(lambda values: np.argmin(values[::-1]), raw=True)
    ) / 25
    pd.testing.assert_frame_equal(loader.factors["aroon_down"].compute(panel), expected_aroon_down)

    expected_dpo = panel.close.shift(11) - panel.close.rolling(20).mean()
    pd.testing.assert_frame_equal(loader.factors["dpo"].compute(panel), expected_dpo)

    delta = panel.close.diff()
    up_sum = delta.clip(lower=0).rolling(20).sum()
    down_sum = (-delta.clip(upper=0)).rolling(20).sum()
    expected_cmo = 100 * (up_sum - down_sum) / (up_sum + down_sum + 1e-10)
    pd.testing.assert_frame_equal(
        loader.factors["chande_momentum_oscillator"].compute(panel), expected_cmo
    )


def test_classic_technical_factors_are_discoverable():
    loader = FactorLoader()
    loader.load("technical_lib")
    loader.load("trading_lib")

    assert {
        "cci", "williams_r", "obv", "chaikin_money_flow", "aroon_up",
        "aroon_down", "dpo", "chande_momentum_oscillator",
    }.issubset(loader.factors)
