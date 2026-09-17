"""价格发现与量价协同因子的确定性验证。"""

import numpy as np
import pandas as pd
import pytest

from factor_test_support import BuiltinFactorLoader as FactorLoader
from app.models.data import Panel
from app.services.factor.base import library_factors
from factor_test_support import builtin_factor_ids


FACTOR_NAMES = {
    "volume_weighted_price_deviation",
    "close_location_persistence",
    "range_return_alignment",
    "range_volume_alignment",
}


def _panel(
    close: pd.DataFrame,
    *,
    volume: pd.DataFrame | None = None,
    high: pd.DataFrame | None = None,
    low: pd.DataFrame | None = None,
) -> Panel:
    open_price = close - 0.5
    if high is None:
        high = close + 1.0
    if low is None:
        low = close - 1.0
    if volume is None:
        volume = pd.DataFrame(
            100.0 + np.arange(len(close), dtype=float)[:, None],
            index=close.index,
            columns=close.columns,
        )
    return Panel(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _sample_panel(periods: int = 100) -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    steps = np.arange(periods, dtype=float)
    close = pd.DataFrame(
        {
            "A": 20.0 + steps * 0.08 + np.sin(steps / 4.0),
            "B": 30.0 + steps * 0.03 + np.cos(steps / 5.0),
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
    return _panel(close, volume=volume)


def _compute(library, name: str, panel: Panel, **params) -> pd.DataFrame:
    library._panel = panel
    return getattr(library, name)(**params)


def _true_range(panel: Panel) -> pd.DataFrame:
    previous_close = panel.close.shift()
    first = panel.high - panel.low
    second = (panel.high - previous_close).abs()
    third = (panel.low - previous_close).abs()
    result = first.where(first >= second, second)
    return result.where(result >= third, third)


def _rolling_correlation(
    left: pd.DataFrame, right: pd.DataFrame, window: int
) -> pd.DataFrame:
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


def test_price_discovery_factors_are_discoverable_and_indexed():
    loader = FactorLoader()
    library = loader.load()
    factors = library_factors(library)

    assert len(factors) == 432
    assert FACTOR_NAMES.issubset(factors)
    assert FACTOR_NAMES.issubset(builtin_factor_ids())


def test_price_discovery_factor_formulae_match_reference_values():
    dates = pd.bdate_range("2024-01-02", periods=6)
    close = pd.DataFrame(
        {"A": [10.0, 12.0, 11.0, 14.0, 13.0, 15.0]}, index=dates
    )
    volume = pd.DataFrame(
        {"A": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}, index=dates
    )
    panel = _panel(close, volume=volume, high=close + 2.0, low=close - 2.0)
    library = FactorLoader().load()

    typical_price = (panel.high + panel.low + panel.close) / 3.0
    weighted_average = (
        (typical_price * panel.volume).rolling(3).sum()
        / panel.volume.rolling(3).sum()
    )
    expected_deviation = (panel.close - weighted_average) / (
        weighted_average.abs() + 1e-10
    )
    pd.testing.assert_frame_equal(
        _compute(
            library,
            "volume_weighted_price_deviation",
            panel,
            window=3,
        ),
        expected_deviation,
    )

    high = pd.DataFrame({"A": [12.0, 13.0, 14.0]}, index=dates[:3])
    low = pd.DataFrame({"A": [8.0, 9.0, 10.0]}, index=dates[:3])
    close_location_close = pd.DataFrame(
        {"A": [11.0, 10.0, 14.0]}, index=dates[:3]
    )
    location_panel = _panel(
        close_location_close,
        high=high,
        low=low,
        volume=pd.DataFrame(100.0, index=dates[:3], columns=["A"]),
    )
    location = _compute(
        library,
        "close_location_persistence",
        location_panel,
        window=3,
    )
    assert location.loc[dates[2], "A"] == pytest.approx(1.0 / 3.0)

    range_panel = _sample_panel(periods=12)
    returns = range_panel.close.pct_change(fill_method=None)
    range_percent = _true_range(range_panel) / (
        range_panel.close.abs() + 1e-10
    )
    expected_return_alignment = _rolling_correlation(
        returns, range_percent, window=4
    )
    pd.testing.assert_frame_equal(
        _compute(
            library,
            "range_return_alignment",
            range_panel,
            window=4,
        ),
        expected_return_alignment,
    )

    expected_volume_alignment = _rolling_correlation(
        range_percent,
        np.log1p(range_panel.volume).diff(),
        window=4,
    )
    pd.testing.assert_frame_equal(
        _compute(
            library,
            "range_volume_alignment",
            range_panel,
            window=4,
        ),
        expected_volume_alignment,
    )


def test_price_discovery_factors_preserve_shape_bounds_and_finiteness():
    loader = FactorLoader()
    loader.load()
    panel = _sample_panel()

    for name in FACTOR_NAMES:
        result = loader.factors[name].compute(panel)
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)
        assert np.isfinite(result.dropna().to_numpy()).all()

    location = loader.factors["close_location_persistence"].compute(panel)
    assert ((location.dropna() >= -1.0) & (location.dropna() <= 1.0)).all().all()
    for name in ("range_return_alignment", "range_volume_alignment"):
        result = loader.factors[name].compute(panel)
        assert ((result.dropna() >= -1.0) & (result.dropna() <= 1.0)).all().all()


def test_flat_ranges_zero_volume_and_missing_values_are_safe():
    dates = pd.bdate_range("2024-01-02", periods=40)
    flat = pd.DataFrame(10.0, index=dates, columns=["A"])
    flat_panel = _panel(flat, high=flat, low=flat)
    loader = FactorLoader()
    library = loader.load()

    for name in FACTOR_NAMES:
        result = _compute(library, name, flat_panel, window=5)
        assert not np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any()
        assert np.isfinite(result.dropna().to_numpy()).all()

    assert (
        _compute(
            library,
            "volume_weighted_price_deviation",
            flat_panel,
            window=5,
        ).dropna()
        == 0.0
    ).all().all()
    assert (
        _compute(library, "close_location_persistence", flat_panel, window=5)
        .dropna()
        == 0.0
    ).all().all()

    zero_volume = flat.copy()
    zero_volume.iloc[:, 0] = 0.0
    zero_volume_panel = _panel(flat, volume=zero_volume, high=flat, low=flat)
    weighted_deviation = _compute(
        library,
        "volume_weighted_price_deviation",
        zero_volume_panel,
        window=5,
    )
    assert weighted_deviation.dropna().empty
    volume_alignment = _compute(
        library,
        "range_volume_alignment",
        zero_volume_panel,
        window=5,
    )
    assert np.isfinite(volume_alignment.dropna().to_numpy()).all()
    assert (volume_alignment.dropna() == 0.0).all().all()

    missing_close = flat.copy()
    missing_close.iloc[20, 0] = np.nan
    missing_panel = _panel(missing_close)
    for name in FACTOR_NAMES:
        result = _compute(library, name, missing_panel, window=5)
        assert not np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any()
        assert result.iloc[20].isna().all()


def test_window_parameters_control_warmup_and_validation():
    panel = _sample_panel()
    loader = FactorLoader()
    library = loader.load()

    assert _compute(
        library,
        "volume_weighted_price_deviation",
        panel,
        window=5,
    ).first_valid_index() == panel.close.index[4]
    assert _compute(
        library,
        "close_location_persistence",
        panel,
        window=5,
    ).first_valid_index() == panel.close.index[4]
    assert _compute(
        library,
        "range_return_alignment",
        panel,
        window=5,
    ).first_valid_index() == panel.close.index[5]
    assert _compute(
        library,
        "range_volume_alignment",
        panel,
        window=5,
    ).first_valid_index() == panel.close.index[5]

    with pytest.raises(ValueError):
        _compute(library, "volume_weighted_price_deviation", panel, window=1)
    with pytest.raises(ValueError):
        _compute(library, "close_location_persistence", panel, window=1)
    with pytest.raises(ValueError):
        _compute(library, "range_return_alignment", panel, window=2)
    with pytest.raises(ValueError):
        _compute(library, "range_volume_alignment", panel, window=2)
    with pytest.raises(ValueError):
        _compute(library, "range_return_alignment", panel, window=True)


def test_price_discovery_factors_do_not_use_future_rows():
    panel = _sample_panel()
    changed_fields = {}
    for field in panel.fields:
        changed = panel[field].copy()
        changed.iloc[50:] = changed.iloc[50:] * 10.0
        changed_fields[field] = changed
    changed_panel = Panel(changed_fields)

    loader = FactorLoader()
    loader.load()
    for name in FACTOR_NAMES:
        baseline = loader.factors[name].compute(panel)
        changed = loader.factors[name].compute(changed_panel)
        pd.testing.assert_frame_equal(
            baseline.iloc[:50], changed.iloc[:50], check_exact=True
        )
