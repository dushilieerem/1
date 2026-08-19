"""日内结构与流动性状态因子的确定性验证。"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from quantcore.factor.base import Panel, library_factors
from researchengine import FactorLoader


FACTOR_NAMES = {
    "overnight_gap_follow_through",
    "range_expansion_persistence",
    "directional_range_balance",
    "volume_impact_score",
}


def _panel(close: pd.DataFrame, *, with_amount: bool = True) -> Panel:
    open_price = close * 0.99
    high = pd.concat([open_price, close], axis=0, keys=["open", "close"]).groupby(level=1).max() + 1.0
    low = pd.concat([open_price, close], axis=0, keys=["open", "close"]).groupby(level=1).min() - 1.0
    volume = pd.DataFrame(
        np.repeat(
            np.linspace(100.0, 250.0, len(close))[:, None],
            len(close.columns),
            axis=1,
        ),
        index=close.index,
        columns=close.columns,
    )
    fields = {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
    if with_amount:
        fields["amount"] = close.abs() * volume * 100.0
    return Panel(fields)


def _sample_panel(periods: int = 140, *, with_amount: bool = True) -> Panel:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    steps = np.arange(periods, dtype=float)
    close = pd.DataFrame(
        {
            "A": 20.0 + steps * 0.08 + np.sin(steps / 4.0),
            "B": 30.0 + np.cos(steps / 5.0) + steps * 0.03,
        },
        index=dates,
    )
    return _panel(close, with_amount=with_amount)


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


def test_intraday_structure_factors_are_discoverable_and_indexed():
    loader = FactorLoader()
    library = loader.load("technical_lib")
    factors = library_factors(library)

    assert len(factors) == 53
    assert FACTOR_NAMES.issubset(factors)

    index_path = Path(__file__).parents[2] / "Factor" / "libraries" / "index.yaml"
    catalog = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    entry = catalog["libraries"]["technical_lib"]
    indexed_names = {item["name"] for item in entry["factors"]}

    assert entry["factor_count"] == len(factors)
    assert FACTOR_NAMES.issubset(indexed_names)


def test_intraday_structure_factor_formulae_match_reference():
    dates = pd.bdate_range("2024-01-02", periods=12)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 10.5, 12.0, 11.5, 13.0, 13.5, 12.5, 14.0, 15.0, 14.5, 16.0]},
        index=dates,
    )
    panel = _panel(close)
    loader = FactorLoader()
    library = loader.load("technical_lib")

    previous_close = panel.close.shift()
    gap = (panel.open - previous_close) / (previous_close.abs() + 1e-10)
    intraday_return = (panel.close - panel.open) / (panel.open.abs() + 1e-10)
    gap_direction = gap.gt(0).astype(float) - gap.lt(0).astype(float)
    expected_gap_follow_through = (
        (gap_direction * intraday_return)
        .where(gap.notna() & intraday_return.notna())
        .rolling(3)
        .mean()
    )
    pd.testing.assert_frame_equal(
        _compute(library, "overnight_gap_follow_through", panel, window=3),
        expected_gap_follow_through,
    )

    true_range = _true_range(panel)
    baseline_range = true_range.rolling(5).mean()
    expected_expansion = (
        true_range.gt(baseline_range)
        .where(true_range.notna() & baseline_range.notna())
        .astype(float)
        .rolling(3)
        .mean()
    )
    pd.testing.assert_frame_equal(
        _compute(
            library,
            "range_expansion_persistence",
            panel,
            window=3,
            baseline=5,
        ),
        expected_expansion,
    )

    change = panel.close - previous_close
    direction = change.gt(0).astype(float) - change.lt(0).astype(float)
    signed_range = (direction * true_range).where(change.notna() & true_range.notna())
    numerator = signed_range.rolling(4).sum()
    denominator = true_range.rolling(4).sum()
    expected_balance = (numerator / (denominator + 1e-10)).where(denominator.notna())
    expected_balance = expected_balance.where(
        denominator.isna() | (denominator > 1e-10), 0.0
    ).clip(lower=-1.0, upper=1.0)
    pd.testing.assert_frame_equal(
        _compute(library, "directional_range_balance", panel, window=4),
        expected_balance,
    )

    returns = panel.close.pct_change(fill_method=None)
    expected_impact = (
        (returns.abs() / panel.amount.where(panel.amount > 0)).rolling(4).mean()
    )
    pd.testing.assert_frame_equal(
        _compute(library, "volume_impact_score", panel, window=4),
        expected_impact,
    )


def test_intraday_structure_factors_preserve_shape_and_have_finite_values():
    loader = FactorLoader()
    loader.load("technical_lib")
    panel = _sample_panel()

    for name in FACTOR_NAMES:
        result = loader.factors[name].compute(panel)
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)
        assert np.isfinite(result.dropna().to_numpy()).all()

    balance = loader.factors["directional_range_balance"].compute(panel)
    assert ((balance.dropna() >= -1.0) & (balance.dropna() <= 1.0)).all().all()
    expansion = loader.factors["range_expansion_persistence"].compute(panel)
    assert ((expansion.dropna() >= 0.0) & (expansion.dropna() <= 1.0)).all().all()


def test_flat_prices_missing_amount_and_missing_values_are_safe():
    dates = pd.bdate_range("2024-01-02", periods=140)
    flat = pd.DataFrame(10.0, index=dates, columns=["A"])
    loader = FactorLoader()
    library = loader.load("technical_lib")

    flat_fields = {
        "open": flat.copy(),
        "high": flat + 1.0,
        "low": flat - 1.0,
        "close": flat.copy(),
        "volume": flat * 10.0,
        "amount": flat * 100.0,
    }
    flat_panel = Panel(flat_fields)
    for name in FACTOR_NAMES:
        result = _compute(library, name, flat_panel, **({"baseline": 20} if name == "range_expansion_persistence" else {}))
        assert np.isfinite(result.dropna().to_numpy()).all()
        assert (result.dropna() == 0.0).all().all()

    fallback_result = _compute(
        library,
        "volume_impact_score",
        Panel({key: value for key, value in flat_fields.items() if key != "amount"}),
        window=5,
    )
    assert np.isfinite(fallback_result.dropna().to_numpy()).all()

    amount = flat.abs() * 100.0
    amount.iloc[80, 0] = 0.0
    zero_amount_panel = Panel(
        {
            "open": flat * 0.99,
            "high": flat + 1.0,
            "low": flat - 1.0,
            "close": flat,
            "volume": flat * 10.0,
            "amount": amount,
        }
    )
    zero_amount = _compute(library, "volume_impact_score", zero_amount_panel, window=5)
    assert zero_amount.iloc[80].isna().all()

    missing = flat.copy()
    missing.iloc[80, 0] = np.nan
    missing_panel = _panel(missing)
    for name in FACTOR_NAMES:
        result = _compute(
            library,
            name,
            missing_panel,
            **({"baseline": 20} if name == "range_expansion_persistence" else {}),
        )
        assert not np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any()
        assert result.iloc[80].isna().any()


def test_window_parameters_change_warmup_and_invalid_values_are_rejected():
    panel = _sample_panel()
    loader = FactorLoader()
    library = loader.load("technical_lib")

    for name in (
        "overnight_gap_follow_through",
        "directional_range_balance",
        "volume_impact_score",
    ):
        short = _compute(library, name, panel, window=4)
        long = _compute(library, name, panel, window=7)
        assert short.first_valid_index() == panel.close.index[4]
        assert long.first_valid_index() == panel.close.index[7]
        with pytest.raises(ValueError):
            _compute(library, name, panel, window=1)

    short_expansion = _compute(
        library, "range_expansion_persistence", panel, window=3, baseline=5
    )
    long_expansion = _compute(
        library, "range_expansion_persistence", panel, window=4, baseline=5
    )
    assert short_expansion.first_valid_index() == panel.close.index[7]
    assert long_expansion.first_valid_index() == panel.close.index[8]
    with pytest.raises(ValueError):
        _compute(library, "range_expansion_persistence", panel, window=1, baseline=5)
    with pytest.raises(ValueError):
        _compute(library, "range_expansion_persistence", panel, window=3, baseline=1)


def test_intraday_structure_factors_do_not_use_future_rows():
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
