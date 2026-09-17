"""成交量结构与时序因子的确定性验证。"""

import numpy as np
import pandas as pd
import pytest

from factor_test_support import BuiltinFactorLoader as FactorLoader
from app.models.data import Panel
from app.services.factor.base import library_factors
from factor_test_support import builtin_factor_ids


FACTOR_NAMES = {
    "up_down_volume_imbalance",
    "volume_concentration",
    "volume_autocorrelation",
    "volume_return_lead_lag",
}


def _panel(close: pd.DataFrame, volume: pd.DataFrame) -> Panel:
    return Panel(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": volume,
        }
    )


def _sample_panel(periods: int = 140) -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    steps = np.arange(periods, dtype=float)
    close = pd.DataFrame(
        {
            "A": 20.0 + steps * 0.08 + np.sin(steps / 4.0),
            "B": 30.0 + np.cos(steps / 5.0) + steps * 0.03,
        },
        index=dates,
    )
    volume = pd.DataFrame(
        {
            "A": 100.0 + 2.0 * steps + 20.0 * np.sin(steps / 6.0),
            "B": 150.0 + 1.5 * steps + 15.0 * np.cos(steps / 7.0),
        },
        index=dates,
    )
    return _panel(close, volume)


def _compute(library, name: str, panel: Panel, **params) -> pd.DataFrame:
    library._panel = panel
    return getattr(library, name)(**params)


def _rolling_correlation(left: pd.DataFrame, right: pd.DataFrame, window: int):
    left_mean = left.rolling(window).mean()
    right_mean = right.rolling(window).mean()
    covariance = (left * right).rolling(window).mean() - left_mean * right_mean
    left_variance = (
        left.pow(2).rolling(window).mean() - left_mean.pow(2)
    ).clip(lower=0.0)
    right_variance = (
        right.pow(2).rolling(window).mean() - right_mean.pow(2)
    ).clip(lower=0.0)
    denominator = np.sqrt(left_variance * right_variance)
    result = covariance / denominator.where(denominator > 1e-10)
    result = result.where(denominator.notna())
    return result.where(
        denominator.isna() | (denominator > 1e-10), 0.0
    ).clip(lower=-1.0, upper=1.0)


def test_volume_structure_factors_are_discoverable_and_indexed():
    loader = FactorLoader()
    library = loader.load()
    factors = library_factors(library)

    assert len(factors) == 432
    assert FACTOR_NAMES.issubset(factors)
    assert FACTOR_NAMES.issubset(builtin_factor_ids())


def test_volume_structure_factor_formulae_match_reference_values():
    dates = pd.bdate_range("2024-01-02", periods=7)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 10.0, 12.0, 11.0, 13.0, 12.0]},
        index=dates,
    )
    volume = pd.DataFrame(
        {"A": [1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 6.0]},
        index=dates,
    )
    panel = _panel(close, volume)
    loader = FactorLoader()
    library = loader.load()

    imbalance = _compute(library, "up_down_volume_imbalance", panel, window=3)
    assert imbalance.loc[dates[3], "A"] == pytest.approx((2.0 - 3.0 + 4.0) / 9.0)

    concentration = _compute(
        library, "volume_concentration", panel, window=4, tail_fraction=0.5
    )
    assert concentration.loc[dates[3], "A"] == pytest.approx(7.0 / 10.0)

    log_volume_change = np.log(volume).diff()
    expected_autocorrelation = _rolling_correlation(
        log_volume_change, log_volume_change.shift(1), window=3
    )
    actual_autocorrelation = _compute(
        library, "volume_autocorrelation", panel, window=3, lag=1
    )
    pd.testing.assert_frame_equal(actual_autocorrelation, expected_autocorrelation)

    returns = close.pct_change(fill_method=None)
    expected_lead_lag = _rolling_correlation(
        returns, log_volume_change.shift(1), window=3
    )
    actual_lead_lag = _compute(
        library, "volume_return_lead_lag", panel, window=3, lag=1
    )
    pd.testing.assert_frame_equal(actual_lead_lag, expected_lead_lag)


def test_volume_structure_factors_preserve_shape_and_bounds():
    loader = FactorLoader()
    loader.load()
    panel = _sample_panel()

    for name in FACTOR_NAMES:
        result = loader.factors[name].compute(panel)
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)
        assert np.isfinite(result.dropna().to_numpy()).all()

    imbalance = loader.factors["up_down_volume_imbalance"].compute(panel)
    assert ((imbalance.dropna() >= -1.0) & (imbalance.dropna() <= 1.0)).all().all()
    concentration = loader.factors["volume_concentration"].compute(panel)
    assert ((concentration.dropna() >= 0.0) & (concentration.dropna() <= 1.0)).all().all()
    for name in ("volume_autocorrelation", "volume_return_lead_lag"):
        result = loader.factors[name].compute(panel)
        assert ((result.dropna() >= -1.0) & (result.dropna() <= 1.0)).all().all()


def test_zero_volume_and_missing_values_are_safe():
    dates = pd.bdate_range("2024-01-02", periods=40)
    close = pd.DataFrame(10.0, index=dates, columns=["A"])
    volume = pd.DataFrame(100.0, index=dates, columns=["A"])
    panel = _panel(close, volume)
    loader = FactorLoader()
    library = loader.load()

    for name in FACTOR_NAMES:
        result = _compute(library, name, panel, **({"window": 5} if name != "volume_concentration" else {"window": 5}))
        assert np.isfinite(result.dropna().to_numpy()).all()

    assert (_compute(library, "up_down_volume_imbalance", panel, window=5).dropna() == 0.0).all().all()
    assert (_compute(library, "volume_autocorrelation", panel, window=5).dropna() == 0.0).all().all()
    assert (_compute(library, "volume_return_lead_lag", panel, window=5).dropna() == 0.0).all().all()
    assert (_compute(library, "volume_concentration", panel, window=5).dropna() == 0.2).all().all()

    zero_volume = volume.copy()
    zero_volume.iloc[20, 0] = 0.0
    zero_panel = _panel(close, zero_volume)
    for name in ("volume_autocorrelation", "volume_return_lead_lag"):
        result = _compute(library, name, zero_panel, window=5)
        assert result.iloc[20:26].isna().any().any()

    missing_volume = volume.copy()
    missing_volume.iloc[20, 0] = np.nan
    missing_panel = _panel(close, missing_volume)
    for name in FACTOR_NAMES:
        result = _compute(library, name, missing_panel, window=5)
        assert not np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any()
        assert result.iloc[20:26].isna().any().any()


def test_parameters_change_warmup_and_invalid_values_are_rejected():
    panel = _sample_panel()
    loader = FactorLoader()
    library = loader.load()

    assert _compute(library, "up_down_volume_imbalance", panel, window=5).first_valid_index() == panel.close.index[5]
    assert _compute(library, "volume_concentration", panel, window=5).first_valid_index() == panel.close.index[4]
    assert _compute(library, "volume_autocorrelation", panel, window=5, lag=1).first_valid_index() == panel.close.index[6]
    assert _compute(library, "volume_return_lead_lag", panel, window=5, lag=2).first_valid_index() == panel.close.index[7]

    with pytest.raises(ValueError):
        _compute(library, "up_down_volume_imbalance", panel, window=1)
    with pytest.raises(ValueError):
        _compute(library, "volume_concentration", panel, window=5, tail_fraction=0.0)
    with pytest.raises(ValueError):
        _compute(library, "volume_concentration", panel, window=5, tail_fraction=1.1)
    with pytest.raises(ValueError):
        _compute(library, "volume_autocorrelation", panel, window=5, lag=5)
    with pytest.raises(ValueError):
        _compute(library, "volume_return_lead_lag", panel, window=5, lag=0)


def test_volume_structure_factors_do_not_use_future_rows():
    panel = _sample_panel()
    changed_volume = panel.volume.copy()
    changed_volume.iloc[80:] = changed_volume.iloc[80:] * 10.0
    changed_panel = _panel(panel.close, changed_volume)

    loader = FactorLoader()
    loader.load()
    for name in FACTOR_NAMES:
        baseline = loader.factors[name].compute(panel)
        changed = loader.factors[name].compute(changed_panel)
        pd.testing.assert_frame_equal(baseline.iloc[:80], changed.iloc[:80], check_exact=True)
