"""收益序列与价格形态状态因子的确定性验证。"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from app.quantcore.factor.base import Panel, library_factors
from app import FactorLoader


FACTOR_NAMES = {
    "return_autocorrelation",
    "gain_loss_asymmetry",
    "wick_reversal_pressure",
    "overnight_gap_share",
}


def _panel(
    close: pd.DataFrame,
    *,
    open_price: pd.DataFrame | None = None,
    high: pd.DataFrame | None = None,
    low: pd.DataFrame | None = None,
) -> Panel:
    if open_price is None:
        open_price = close * 0.99
    body_top = open_price.where(open_price >= close, close)
    body_bottom = open_price.where(open_price <= close, close)
    if high is None:
        high = body_top + 1.0
    if low is None:
        low = body_bottom - 1.0
    volume = pd.DataFrame(
        100.0,
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
    return _panel(close)


def _compute(library, name: str, panel: Panel, **params) -> pd.DataFrame:
    library._panel = panel
    return getattr(library, name)(**params)


def test_return_shape_factors_are_discoverable_and_indexed():
    loader = FactorLoader()
    library = loader.load("technical_lib")
    factors = library_factors(library)

    assert len(factors) == 57
    assert FACTOR_NAMES.issubset(factors)

    from app.assets.factors import INDEX_PATH

    index_path = INDEX_PATH
    catalog = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    entry = catalog["libraries"]["technical_lib"]
    indexed_names = {item["name"] for item in entry["factors"]}

    assert entry["factor_count"] == len(factors)
    assert FACTOR_NAMES.issubset(indexed_names)


def test_return_shape_factor_formulae_match_hand_calculated_values():
    dates = pd.bdate_range("2024-01-02", periods=6)
    alternating = pd.DataFrame(
        {"A": [100.0, 101.0, 100.0, 101.0, 100.0, 101.0]},
        index=dates,
    )
    loader = FactorLoader()
    library = loader.load("technical_lib")

    autocorrelation = _compute(
        library,
        "return_autocorrelation",
        _panel(alternating),
        window=3,
        lag=1,
    )
    assert autocorrelation.loc[dates[4], "A"] == pytest.approx(-1.0)

    gains_and_losses = pd.DataFrame(
        {"A": [100.0, 110.0, 99.0, 108.9]},
        index=dates[:4],
    )
    asymmetry = _compute(
        library,
        "gain_loss_asymmetry",
        _panel(gains_and_losses),
        window=3,
    )
    assert asymmetry.loc[dates[3], "A"] == pytest.approx(np.log(2.0))

    candle_dates = dates[:3]
    candle_close = pd.DataFrame({"A": [11.0, 9.0, 10.0]}, index=candle_dates)
    candle_open = pd.DataFrame({"A": [10.0, 10.0, 10.0]}, index=candle_dates)
    candle_high = pd.DataFrame({"A": [13.0, 11.0, 11.0]}, index=candle_dates)
    candle_low = pd.DataFrame({"A": [9.0, 8.0, 9.0]}, index=candle_dates)
    pressure = _compute(
        library,
        "wick_reversal_pressure",
        _panel(
            candle_close,
            open_price=candle_open,
            high=candle_high,
            low=candle_low,
        ),
        window=2,
    )
    assert pressure.loc[candle_dates[1], "A"] == pytest.approx(-1.0 / 8.0)

    gap_close = pd.DataFrame({"A": [10.0, 12.0, 11.0, 13.0]}, index=dates[:4])
    gap_open = pd.DataFrame({"A": [10.0, 14.0, 11.0, 15.0]}, index=dates[:4])
    gap_high = pd.DataFrame({"A": [11.0, 15.0, 12.0, 16.0]}, index=dates[:4])
    gap_low = pd.DataFrame({"A": [9.0, 11.0, 10.0, 12.0]}, index=dates[:4])
    gap_share = _compute(
        library,
        "overnight_gap_share",
        _panel(
            gap_close,
            open_price=gap_open,
            high=gap_high,
            low=gap_low,
        ),
        window=2,
    )
    assert gap_share.loc[dates[2], "A"] == pytest.approx(5.0 / 7.0)


def test_return_shape_factors_preserve_shape_and_bounds():
    loader = FactorLoader()
    loader.load("technical_lib")
    panel = _sample_panel()

    for name in FACTOR_NAMES:
        result = loader.factors[name].compute(panel)
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)
        assert np.isfinite(result.dropna().to_numpy()).all()

    autocorrelation = loader.factors["return_autocorrelation"].compute(panel)
    assert ((autocorrelation.dropna() >= -1.0) & (autocorrelation.dropna() <= 1.0)).all().all()
    pressure = loader.factors["wick_reversal_pressure"].compute(panel)
    assert ((pressure.dropna() >= -1.0) & (pressure.dropna() <= 1.0)).all().all()
    gap_share = loader.factors["overnight_gap_share"].compute(panel)
    assert ((gap_share.dropna() >= 0.0) & (gap_share.dropna() <= 1.0)).all().all()


def test_zero_ranges_and_missing_values_are_safe():
    dates = pd.bdate_range("2024-01-02", periods=60)
    flat = pd.DataFrame(10.0, index=dates, columns=["A"])
    zero_range_panel = _panel(flat, open_price=flat, high=flat, low=flat)
    loader = FactorLoader()
    library = loader.load("technical_lib")

    for name in FACTOR_NAMES:
        result = _compute(library, name, zero_range_panel)
        assert np.isfinite(result.dropna().to_numpy()).all()
        assert (result.dropna() == 0.0).all().all()

    missing_fields = {
        field: zero_range_panel[field].copy() for field in zero_range_panel.fields
    }
    for field in ("open", "high", "low", "close"):
        missing_fields[field].iloc[30, 0] = np.nan
    missing_panel = Panel(missing_fields)
    for name in FACTOR_NAMES:
        result = _compute(library, name, missing_panel)
        assert not np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any()
        assert result.iloc[30].isna().all()


def test_window_parameters_change_warmup_and_invalid_values_are_rejected():
    panel = _sample_panel()
    loader = FactorLoader()
    library = loader.load("technical_lib")

    short_auto = _compute(
        library, "return_autocorrelation", panel, window=5, lag=1
    )
    long_auto = _compute(
        library, "return_autocorrelation", panel, window=8, lag=1
    )
    lagged_auto = _compute(
        library, "return_autocorrelation", panel, window=5, lag=2
    )
    assert short_auto.first_valid_index() == panel.close.index[6]
    assert long_auto.first_valid_index() == panel.close.index[9]
    assert lagged_auto.first_valid_index() == panel.close.index[7]

    assert _compute(library, "gain_loss_asymmetry", panel, window=5).first_valid_index() == panel.close.index[5]
    assert _compute(library, "wick_reversal_pressure", panel, window=5).first_valid_index() == panel.close.index[4]
    assert _compute(library, "overnight_gap_share", panel, window=5).first_valid_index() == panel.close.index[5]

    with pytest.raises(ValueError):
        _compute(library, "return_autocorrelation", panel, window=1, lag=1)
    with pytest.raises(ValueError):
        _compute(library, "return_autocorrelation", panel, window=5, lag=0)
    with pytest.raises(ValueError):
        _compute(library, "return_autocorrelation", panel, window=5, lag=5)
    for name in ("gain_loss_asymmetry", "wick_reversal_pressure", "overnight_gap_share"):
        with pytest.raises(ValueError):
            _compute(library, name, panel, window=1)


def test_return_shape_factors_do_not_use_future_rows():
    panel = _sample_panel()
    changed_fields = {}
    for field in panel.fields:
        changed = panel[field].copy()
        changed.iloc[80:] = changed.iloc[80:] * 10.0
        changed_fields[field] = changed
    changed_panel = Panel(changed_fields)

    loader = FactorLoader()
    loader.load("technical_lib")
    for name in FACTOR_NAMES:
        baseline = loader.factors[name].compute(panel)
        changed = loader.factors[name].compute(changed_panel)
        pd.testing.assert_frame_equal(baseline.iloc[:80], changed.iloc[:80], check_exact=True)
