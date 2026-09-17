"""收益路径与市场状态因子的确定性验证。"""

import numpy as np
import pandas as pd
import pytest

from factor_test_support import BuiltinFactorLoader as FactorLoader
from app.models.data import Panel
from app.services.factor.base import library_factors
from factor_test_support import builtin_factor_ids


FACTOR_NAMES = {
    "return_sign_entropy",
    "volatility_clustering",
    "drawdown_recovery_fraction",
    "cross_sectional_return_dispersion",
}


def _panel(close: pd.DataFrame) -> Panel:
    return Panel({"close": close})


def _sample_panel(periods: int = 120, symbols: int = 3) -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    steps = np.arange(periods, dtype=float)
    close = pd.DataFrame(
        {
            f"S{index}": 30.0
            + (index + 1) * 0.06 * steps
            + np.sin(steps / (3.5 + index)) * (0.8 + index * 0.2)
            + np.cos(steps / (7.0 + index)) * 0.3
            for index in range(symbols)
        },
        index=dates,
    )
    return _panel(close)


def _compute(library, name: str, panel: Panel, **params) -> pd.DataFrame:
    library._panel = panel
    return getattr(library, name)(**params)


def _rolling_correlation(
    left: pd.DataFrame, right: pd.DataFrame, window: int
) -> pd.DataFrame:
    left_mean = left.rolling(window, min_periods=window).mean()
    right_mean = right.rolling(window, min_periods=window).mean()
    covariance = (
        (left * right).rolling(window, min_periods=window).mean()
        - left_mean * right_mean
    )
    left_variance = (
        left.pow(2).rolling(window, min_periods=window).mean()
        - left_mean.pow(2)
    ).clip(lower=0.0)
    right_variance = (
        right.pow(2).rolling(window, min_periods=window).mean()
        - right_mean.pow(2)
    ).clip(lower=0.0)
    denominator = np.sqrt(left_variance * right_variance)
    result = covariance / denominator.where(denominator > 1e-10)
    result = result.where(denominator.notna())
    return result.where(
        denominator.isna() | (denominator > 1e-10), 0.0
    ).clip(lower=-1.0, upper=1.0)


def test_market_state_factors_are_discoverable_and_indexed():
    loader = FactorLoader()
    library = loader.load()
    factors = library_factors(library)

    assert len(factors) == 432
    assert FACTOR_NAMES.issubset(factors)
    assert FACTOR_NAMES.issubset(builtin_factor_ids())


def test_market_state_factor_formulae_match_reference_values():
    dates = pd.bdate_range("2024-01-02", periods=6)
    close = pd.DataFrame(
        {"A": [100.0, 110.0, 99.0, 99.0, 108.0, 105.0]},
        index=dates,
    )
    panel = _panel(close)
    library = FactorLoader().load()

    result = _compute(library, "return_sign_entropy", panel, window=4)
    probabilities = (0.5, 0.25, 0.25)
    expected_entropy = -sum(
        probability * np.log(probability) for probability in probabilities
    ) / np.log(3.0)
    assert result.loc[dates[4], "A"] == pytest.approx(expected_entropy)

    returns = close.pct_change(fill_method=None)
    squared_returns = returns.pow(2)
    expected_clustering = _rolling_correlation(
        squared_returns,
        squared_returns.shift(1),
        window=4,
    )
    pd.testing.assert_frame_equal(
        _compute(
            library,
            "volatility_clustering",
            panel,
            window=4,
        ),
        expected_clustering,
    )

    recovery_close = pd.DataFrame(
        {"A": [100.0, 90.0, 92.0, 93.0, 94.0]},
        index=dates[:5],
    )
    recovery = _compute(
        library,
        "drawdown_recovery_fraction",
        _panel(recovery_close),
        window=5,
    )
    assert recovery.loc[dates[4], "A"] == pytest.approx(0.4)

    cross_close = pd.DataFrame(
        {
            "A": [100.0, 110.0, 99.0, 108.0, 105.0],
            "B": [100.0, 105.0, 105.0, 100.0, 110.0],
            "C": [100.0, 100.0, 110.0, 110.0, 99.0],
        },
        index=dates[:5],
    )
    cross_returns = cross_close.pct_change(fill_method=None)
    daily_dispersion = cross_returns.std(axis=1, ddof=0).where(
        cross_returns.notna().sum(axis=1) >= 2
    )
    expected_dispersion = daily_dispersion.rolling(3, min_periods=3).mean()
    expected_cross = pd.DataFrame(
        np.broadcast_to(
            expected_dispersion.to_numpy()[:, None],
            cross_close.shape,
        ).copy(),
        index=cross_close.index,
        columns=cross_close.columns,
    )
    pd.testing.assert_frame_equal(
        _compute(
            library,
            "cross_sectional_return_dispersion",
            _panel(cross_close),
            window=3,
        ),
        expected_cross,
    )


def test_market_state_factors_preserve_shape_bounds_and_finiteness():
    loader = FactorLoader()
    loader.load()
    panel = _sample_panel()

    for name in FACTOR_NAMES:
        result = loader.factors[name].compute(panel)
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)
        assert np.isfinite(result.dropna().to_numpy()).all()

    entropy = loader.factors["return_sign_entropy"].compute(panel).dropna()
    assert ((entropy >= 0.0) & (entropy <= 1.0)).all().all()

    clustering = loader.factors["volatility_clustering"].compute(panel).dropna()
    assert ((clustering >= -1.0) & (clustering <= 1.0)).all().all()

    recovery = loader.factors["drawdown_recovery_fraction"].compute(panel).dropna()
    assert ((recovery >= 0.0) & (recovery <= 1.0)).all().all()

    dispersion = loader.factors["cross_sectional_return_dispersion"].compute(panel).dropna()
    assert (dispersion >= 0.0).all().all()


def test_flat_prices_and_missing_values_are_safe():
    dates = pd.bdate_range("2024-01-02", periods=80)
    flat = pd.DataFrame(10.0, index=dates, columns=["A", "B", "C"])
    loader = FactorLoader()
    library = loader.load()

    for name in FACTOR_NAMES:
        result = _compute(library, name, _panel(flat), window=5)
        assert not np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any()
        assert np.isfinite(result.dropna().to_numpy()).all()

    assert (
        _compute(library, "return_sign_entropy", _panel(flat), window=5)
        .dropna()
        == 0.0
    ).all().all()
    assert (
        _compute(library, "volatility_clustering", _panel(flat), window=5)
        .dropna()
        == 0.0
    ).all().all()
    assert (
        _compute(library, "drawdown_recovery_fraction", _panel(flat), window=5)
        .dropna()
        == 1.0
    ).all().all()
    assert (
        _compute(
            library,
            "cross_sectional_return_dispersion",
            _panel(flat),
            window=5,
        ).dropna()
        == 0.0
    ).all().all()

    missing = flat.copy()
    missing.iloc[30, 0] = np.nan
    for name in FACTOR_NAMES:
        result = _compute(library, name, _panel(missing), window=5)
        assert not np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any()


def test_window_parameters_control_warmup_and_validation():
    panel = _sample_panel()
    loader = FactorLoader()
    library = loader.load()

    assert _compute(
        library,
        "return_sign_entropy",
        panel,
        window=5,
    ).first_valid_index() == panel.close.index[5]
    assert _compute(
        library,
        "volatility_clustering",
        panel,
        window=5,
    ).first_valid_index() == panel.close.index[6]
    assert _compute(
        library,
        "drawdown_recovery_fraction",
        panel,
        window=5,
    ).first_valid_index() == panel.close.index[4]
    assert _compute(
        library,
        "cross_sectional_return_dispersion",
        panel,
        window=5,
    ).first_valid_index() == panel.close.index[5]

    with pytest.raises(ValueError):
        _compute(library, "return_sign_entropy", panel, window=0)
    with pytest.raises(ValueError):
        _compute(library, "drawdown_recovery_fraction", panel, window=3)
    with pytest.raises(ValueError):
        _compute(library, "volatility_clustering", panel, window=3)
    with pytest.raises(ValueError):
        _compute(library, "volatility_clustering", panel, window=5, lag=5)
    with pytest.raises(ValueError):
        _compute(library, "volatility_clustering", panel, window=5, lag=True)


def test_market_state_factors_do_not_use_future_rows():
    panel = _sample_panel()
    changed_close = panel.close.copy()
    changed_close.iloc[60:] = changed_close.iloc[60:] * 10.0
    changed_panel = _panel(changed_close)

    loader = FactorLoader()
    loader.load()
    for name in FACTOR_NAMES:
        baseline = loader.factors[name].compute(panel)
        changed = loader.factors[name].compute(changed_panel)
        pd.testing.assert_frame_equal(
            baseline.iloc[:60],
            changed.iloc[:60],
            check_exact=True,
        )
