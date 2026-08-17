"""趋势质量与路径风险因子的确定性验证。"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from quantcore.factor.base import Panel, library_factors
from researchengine import FactorLoader


FACTOR_NAMES = {
    "kaufman_efficiency_ratio",
    "normalized_linear_regression_slope",
    "regression_r_squared",
    "ulcer_index",
}


def _panel(close: pd.DataFrame) -> Panel:
    return Panel(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": close * 100,
        }
    )


def _sample_panel(periods: int = 80) -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    close = pd.DataFrame(
        {
            "A": np.arange(10, 10 + periods, dtype=float),
            "B": 30 + np.sin(np.arange(periods, dtype=float) / 3),
        },
        index=dates,
    )
    return _panel(close)


def _compute(library, name: str, panel: Panel, **params) -> pd.DataFrame:
    library._panel = panel
    return getattr(library, name)(**params)


def test_trend_quality_factors_are_discoverable_and_indexed():
    loader = FactorLoader()
    library = loader.load("technical_lib")
    factors = library_factors(library)

    assert len(factors) == 49
    assert FACTOR_NAMES.issubset(factors)

    index_path = Path(__file__).parents[2] / "Factor" / "libraries" / "index.yaml"
    catalog = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    entry = catalog["libraries"]["technical_lib"]
    indexed_names = {item["name"] for item in entry["factors"]}

    assert entry["factor_count"] == len(factors)
    assert FACTOR_NAMES.issubset(indexed_names)


def test_trend_quality_factors_preserve_panel_shape_and_finite_values():
    loader = FactorLoader()
    loader.load("technical_lib")
    panel = _sample_panel()

    for name in FACTOR_NAMES:
        result = loader.factors[name].compute(panel)
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)
        assert np.isfinite(result.dropna().to_numpy()).all()


def test_trend_quality_factors_match_hand_calculated_values():
    dates = pd.bdate_range("2024-01-02", periods=5)
    panel = _panel(pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=dates))
    loader = FactorLoader()
    library = loader.load("technical_lib")

    efficiency = _compute(library, "kaufman_efficiency_ratio", panel, window=4)
    assert efficiency.loc[dates[-1], "A"] == pytest.approx(1.0)

    slope = _compute(
        library,
        "normalized_linear_regression_slope",
        panel, window=5
    )
    assert slope.loc[dates[-1], "A"] == pytest.approx(1.0 / 3.0)

    r_squared = _compute(library, "regression_r_squared", panel, window=5)
    assert r_squared.loc[dates[-1], "A"] == pytest.approx(1.0)

    drawdown = np.array([np.nan, np.nan, -100 / 12, -25.0, -100 / 11])
    expected_ulcer = np.sqrt(np.mean(drawdown[-3:] ** 2))
    ulcer_panel = _panel(
        pd.DataFrame({"A": [10.0, 12.0, 11.0, 9.0, 10.0]}, index=dates)
    )
    ulcer = _compute(library, "ulcer_index", ulcer_panel, window=3)
    assert ulcer.loc[dates[-1], "A"] == pytest.approx(expected_ulcer)


def test_flat_prices_and_missing_values_are_safe():
    dates = pd.bdate_range("2024-01-02", periods=30)
    flat = _panel(pd.DataFrame({"A": np.full(30, 10.0)}, index=dates))
    loader = FactorLoader()
    library = loader.load("technical_lib")

    for name in FACTOR_NAMES:
        result = _compute(library, name, flat, window=5)
        assert np.isfinite(result.dropna().to_numpy()).all()
        assert (result.dropna() == 0.0).all().all()

    close = flat.close.copy()
    close.iloc[12, 0] = np.nan
    panel_with_missing = _panel(close)
    for name in FACTOR_NAMES:
        result = _compute(library, name, panel_with_missing, window=5)
        assert not np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any()
        assert result.isna().iloc[12].any()


def test_window_changes_warmup_and_invalid_windows_are_rejected():
    panel = _sample_panel()
    loader = FactorLoader()
    library = loader.load("technical_lib")

    for name in (
        "kaufman_efficiency_ratio",
        "normalized_linear_regression_slope",
        "regression_r_squared",
    ):
        short = _compute(library, name, panel, window=5)
        long = _compute(library, name, panel, window=8)
        expected_short = 5 if name == "kaufman_efficiency_ratio" else 4
        expected_long = 8 if name == "kaufman_efficiency_ratio" else 7
        assert short.first_valid_index() == panel.close.index[expected_short]
        assert long.first_valid_index() == panel.close.index[expected_long]
        with pytest.raises(ValueError):
            _compute(library, name, panel, window=1)

    short_ulcer = _compute(library, "ulcer_index", panel, window=5)
    long_ulcer = _compute(library, "ulcer_index", panel, window=8)
    assert short_ulcer.first_valid_index() == panel.close.index[8]
    assert long_ulcer.first_valid_index() == panel.close.index[14]
    with pytest.raises(ValueError):
        _compute(library, "ulcer_index", panel, window=1)


def test_trend_quality_factors_do_not_use_future_prices():
    panel = _sample_panel()
    changed_close = panel.close.copy()
    changed_close.iloc[40:] = changed_close.iloc[40:] * 10
    changed_panel = _panel(changed_close)
    loader = FactorLoader()
    loader.load("technical_lib")

    for name in FACTOR_NAMES:
        baseline = loader.factors[name].compute(panel)
        changed = loader.factors[name].compute(changed_panel)
        pd.testing.assert_frame_equal(
            baseline.iloc[:40],
            changed.iloc[:40],
            check_exact=True,
        )
