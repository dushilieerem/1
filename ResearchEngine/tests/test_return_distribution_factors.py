"""收益分布与方向广度因子的确定性验证。"""

import numpy as np
import pandas as pd
import pytest
import yaml

from app import FactorLoader
from app.quantcore.factor.base import Panel, library_factors


FACTOR_NAMES = {
    "up_down_frequency_imbalance",
    "return_tail_balance",
    "return_sign_flip_rate",
    "return_shock_frequency",
}


def _panel(close: pd.DataFrame) -> Panel:
    return Panel(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": pd.DataFrame(
                100.0, index=close.index, columns=close.columns
            ),
        }
    )


def _sample_panel(periods: int = 140) -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    steps = np.arange(periods, dtype=float)
    returns = 0.002 * np.sin(steps / 3.0) + 0.0015 * np.cos(steps / 7.0)
    close_a = 20.0 * np.exp(np.cumsum(returns))
    close_b = 30.0 * np.exp(
        np.cumsum(0.001 * np.cos(steps / 4.0) - 0.001 * np.sin(steps / 9.0))
    )
    close = pd.DataFrame({"A": close_a, "B": close_b}, index=dates)
    return _panel(close)


def _compute(library, name: str, panel: Panel, **params) -> pd.DataFrame:
    library._panel = panel
    return getattr(library, name)(**params)


def _tail_balance(values: np.ndarray, tail_fraction: float) -> float:
    tail_size = max(1, int(np.ceil(values.size * tail_fraction)))
    ordered = np.sort(values)
    lower = ordered[:tail_size].mean()
    upper = ordered[-tail_size:].mean()
    return (upper + lower) / (abs(upper) + abs(lower) + 1e-10)


def test_return_distribution_factors_are_discoverable_and_indexed():
    loader = FactorLoader()
    library = loader.load("technical_lib")
    factors = library_factors(library)

    assert FACTOR_NAMES.issubset(factors)

    from app.assets.factors import INDEX_PATH

    catalog = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8"))
    entry = catalog["libraries"]["technical_lib"]
    indexed_names = {item["name"] for item in entry["factors"]}

    assert entry["factor_count"] == len(factors)
    assert FACTOR_NAMES.issubset(indexed_names)


def test_return_distribution_factor_formulae_match_reference_values():
    dates = pd.bdate_range("2024-01-02", periods=8)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 10.0, 12.0, 11.0, 13.0, 12.0, 14.0]},
        index=dates,
    )
    panel = _panel(close)
    library = FactorLoader().load("technical_lib")

    imbalance = _compute(
        library, "up_down_frequency_imbalance", panel, window=3
    )
    assert imbalance.loc[dates[3], "A"] == pytest.approx(1.0 / 3.0)

    returns = close.pct_change(fill_method=None)
    tail = _compute(
        library, "return_tail_balance", panel, window=4, tail_fraction=0.5
    )
    expected_tail = _tail_balance(returns.iloc[1:5, 0].to_numpy(), 0.5)
    assert tail.loc[dates[4], "A"] == pytest.approx(expected_tail)

    flip_rate = _compute(library, "return_sign_flip_rate", panel, window=3)
    assert flip_rate.loc[dates[4], "A"] == pytest.approx(1.0)

    shock = _compute(
        library,
        "return_shock_frequency",
        panel,
        window=4,
        shock_multiple=1.5,
    )
    window_returns = returns.iloc[1:5, 0].to_numpy()
    threshold = 1.5 * np.median(np.abs(window_returns))
    expected_shock = np.mean(np.abs(window_returns) > threshold)
    assert shock.loc[dates[4], "A"] == pytest.approx(expected_shock)


def test_return_distribution_factors_preserve_shape_bounds_and_finiteness():
    panel = _sample_panel()
    loader = FactorLoader()
    loader.load("technical_lib")

    for name in FACTOR_NAMES:
        result = loader.factors[name].compute(panel)
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)
        assert np.isfinite(result.dropna().to_numpy()).all()

    imbalance = loader.factors["up_down_frequency_imbalance"].compute(panel)
    assert ((imbalance.dropna() >= -1.0) & (imbalance.dropna() <= 1.0)).all().all()

    tail = loader.factors["return_tail_balance"].compute(panel)
    assert ((tail.dropna() >= -1.0) & (tail.dropna() <= 1.0)).all().all()

    for name in ("return_sign_flip_rate", "return_shock_frequency"):
        result = loader.factors[name].compute(panel)
        assert ((result.dropna() >= 0.0) & (result.dropna() <= 1.0)).all().all()


def test_zero_constant_and_missing_returns_are_safe():
    dates = pd.bdate_range("2024-01-02", periods=40)
    close = pd.DataFrame(10.0, index=dates, columns=["A"])
    panel = _panel(close)
    library = FactorLoader().load("technical_lib")

    for name in FACTOR_NAMES:
        result = _compute(library, name, panel, **({"window": 5} if name != "return_tail_balance" else {"window": 5}))
        assert np.isfinite(result.dropna().to_numpy()).all()
        assert not result.dropna().empty

    assert (
        _compute(library, "up_down_frequency_imbalance", panel, window=5)
        .dropna()
        .eq(0.0)
        .all()
        .all()
    )
    assert (
        _compute(library, "return_tail_balance", panel, window=5)
        .dropna()
        .eq(0.0)
        .all()
        .all()
    )
    assert (
        _compute(library, "return_sign_flip_rate", panel, window=5)
        .dropna()
        .eq(0.0)
        .all()
        .all()
    )
    assert (
        _compute(library, "return_shock_frequency", panel, window=5)
        .dropna()
        .eq(0.0)
        .all()
        .all()
    )

    missing_close = close.copy()
    missing_close.iloc[20, 0] = np.nan
    missing_result = _compute(
        library,
        "return_tail_balance",
        _panel(missing_close),
        window=5,
    )
    assert missing_result.iloc[20:27].isna().any().any()
    assert not np.isinf(missing_result.to_numpy(dtype=float, na_value=np.nan)).any()

    zero_close = close.copy()
    zero_close.iloc[20, 0] = 0.0
    zero_result = _compute(
        library,
        "return_shock_frequency",
        _panel(zero_close),
        window=5,
    )
    assert not np.isinf(zero_result.to_numpy(dtype=float, na_value=np.nan)).any()
    assert zero_result.iloc[20:27].isna().any().any()


def test_parameters_change_warmup_and_invalid_values_are_rejected():
    panel = _sample_panel()
    library = FactorLoader().load("technical_lib")

    assert (
        _compute(library, "up_down_frequency_imbalance", panel, window=5)
        .first_valid_index()
        == panel.close.index[5]
    )
    assert (
        _compute(library, "return_tail_balance", panel, window=5)
        .first_valid_index()
        == panel.close.index[5]
    )
    assert (
        _compute(library, "return_sign_flip_rate", panel, window=5)
        .first_valid_index()
        == panel.close.index[6]
    )
    assert (
        _compute(library, "return_shock_frequency", panel, window=5)
        .first_valid_index()
        == panel.close.index[5]
    )

    tail_short = _compute(
        library, "return_tail_balance", panel, window=8, tail_fraction=0.2
    )
    tail_wide = _compute(
        library, "return_tail_balance", panel, window=8, tail_fraction=0.5
    )
    assert not tail_short.dropna().equals(tail_wide.dropna())

    shock_low = _compute(
        library, "return_shock_frequency", panel, window=8, shock_multiple=1.0
    )
    shock_high = _compute(
        library, "return_shock_frequency", panel, window=8, shock_multiple=3.0
    )
    assert not shock_low.dropna().equals(shock_high.dropna())

    with pytest.raises(ValueError):
        _compute(library, "up_down_frequency_imbalance", panel, window=1)
    with pytest.raises(ValueError):
        _compute(library, "return_tail_balance", panel, window=3)
    with pytest.raises(ValueError):
        _compute(library, "return_tail_balance", panel, window=5, tail_fraction=0.0)
    with pytest.raises(ValueError):
        _compute(library, "return_tail_balance", panel, window=5, tail_fraction=0.6)
    with pytest.raises(ValueError):
        _compute(library, "return_shock_frequency", panel, window=5, shock_multiple=0)
    with pytest.raises(ValueError):
        _compute(
            library,
            "return_shock_frequency",
            panel,
            window=5,
            shock_multiple=np.inf,
        )


def test_return_distribution_factors_do_not_use_future_rows():
    panel = _sample_panel()
    changed_close = panel.close.copy()
    changed_close.iloc[80:] = changed_close.iloc[80:] * 1.5
    changed_panel = _panel(changed_close)

    loader = FactorLoader()
    loader.load("technical_lib")
    for name in FACTOR_NAMES:
        baseline = loader.factors[name].compute(panel)
        changed = loader.factors[name].compute(changed_panel)
        pd.testing.assert_frame_equal(
            baseline.iloc[:80], changed.iloc[:80], check_exact=True
        )
