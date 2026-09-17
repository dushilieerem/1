"""波动结构与尾部风险因子的确定性验证。"""

import numpy as np
import pandas as pd
import pytest

from app.models.data import Panel
from app.services.factor.base import library_factors
from factor_test_support import BuiltinFactorLoader as FactorLoader
from factor_test_support import builtin_factor_ids


FACTOR_NAMES = {
    "atr_percent",
    "atr_percentile",
    "intraday_to_close_vol_ratio",
    "tail_loss_concentration",
}


def _panel(close: pd.DataFrame) -> Panel:
    open_price = close * 0.995
    high = close + 1.0
    low = close - 0.8
    volume = pd.DataFrame(
        np.repeat(
            np.linspace(100.0, 250.0, len(close))[:, None],
            len(close.columns),
            axis=1,
        ),
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
            "B": 30.0 + steps * 0.03 + np.cos(steps / 5.0),
        },
        index=dates,
    )
    return _panel(close)


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


def _last_percentile_rank(values: np.ndarray) -> float:
    current = values[-1]
    less = np.count_nonzero(values < current)
    equal = np.count_nonzero(values == current)
    return (less + 0.5 * equal) / values.size


def test_volatility_structure_factors_are_discoverable_and_indexed():
    loader = FactorLoader()
    library = loader.load()
    factors = library_factors(library)

    assert len(factors) == 432
    assert FACTOR_NAMES.issubset(factors)
    assert FACTOR_NAMES.issubset(builtin_factor_ids())


def test_volatility_structure_factor_formulae_match_reference():
    dates = pd.bdate_range("2024-01-02", periods=8)
    close = pd.DataFrame(
        {"A": [10.0, 11.0, 10.5, 12.0, 11.5, 13.0, 12.0, 14.0]},
        index=dates,
    )
    panel = _panel(close)
    loader = FactorLoader()
    library = loader.load()

    true_range = _true_range(panel)
    expected_atr = true_range.rolling(2).mean() / panel.close.abs()
    pd.testing.assert_frame_equal(
        _compute(library, "atr_percent", panel, window=2), expected_atr
    )

    expected_atr_rank = expected_atr.rolling(3).apply(
        _last_percentile_rank, raw=True
    )
    pd.testing.assert_frame_equal(
        _compute(
            library,
            "atr_percentile",
            panel,
            window=2,
            rank_window=3,
        ),
        expected_atr_rank,
    )

    high = panel.high.where(panel.high > 1e-10)
    low = panel.low.where(panel.low > 1e-10)
    range_log_return = np.log(high / low).replace([np.inf, -np.inf], np.nan)
    range_volatility = np.sqrt(
        range_log_return.pow(2).rolling(3).mean().clip(lower=0.0)
    )
    close_log_return = np.log(
        panel.close.where(panel.close > 1e-10)
        / panel.close.where(panel.close > 1e-10).shift()
    ).replace([np.inf, -np.inf], np.nan)
    close_volatility = close_log_return.rolling(3).std(ddof=0)
    expected_ratio = range_volatility / close_volatility.where(
        close_volatility > 1e-10
    )
    pd.testing.assert_frame_equal(
        _compute(library, "intraday_to_close_vol_ratio", panel, window=3),
        expected_ratio,
    )

    tail_close = pd.DataFrame(
        {"A": [100.0, 102.0, 101.0, 99.0, 98.0]}, index=dates[:5]
    )
    tail_panel = _panel(tail_close)
    returns = tail_panel.close["A"].pct_change(fill_method=None).iloc[1:5]
    losses = -returns[returns < 0.0].to_numpy()
    expected_tail = np.sort(losses)[-2:].sum() / losses.sum()
    result = _compute(
        library,
        "tail_loss_concentration",
        tail_panel,
        window=4,
        tail_fraction=0.5,
    )
    assert result.loc[dates[4], "A"] == pytest.approx(expected_tail)


def test_volatility_structure_factors_preserve_shape_and_bounds():
    loader = FactorLoader()
    loader.load()
    panel = _sample_panel()

    for name in FACTOR_NAMES:
        result = loader.factors[name].compute(panel)
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)
        assert np.isfinite(result.dropna().to_numpy()).all()

    atr = loader.factors["atr_percent"].compute(panel)
    assert (atr.dropna() >= 0.0).all().all()

    atr_rank = loader.factors["atr_percentile"].compute(panel)
    assert ((atr_rank.dropna() >= 0.0) & (atr_rank.dropna() <= 1.0)).all().all()

    ratio = loader.factors["intraday_to_close_vol_ratio"].compute(panel)
    assert (ratio.dropna() >= 0.0).all().all()

    tail = loader.factors["tail_loss_concentration"].compute(panel)
    assert ((tail.dropna() >= 0.0) & (tail.dropna() <= 1.0)).all().all()


def test_flat_prices_missing_values_and_zero_denominators_are_safe():
    dates = pd.bdate_range("2024-01-02", periods=100)
    flat = pd.DataFrame(10.0, index=dates, columns=["A"])
    panel = Panel(
        {
            "open": flat.copy(),
            "high": flat.copy(),
            "low": flat.copy(),
            "close": flat.copy(),
            "volume": flat * 10.0,
        }
    )
    loader = FactorLoader()
    library = loader.load()

    atr = _compute(library, "atr_percent", panel, window=5)
    assert np.isfinite(atr.dropna().to_numpy()).all()
    assert (atr.dropna() == 0.0).all().all()

    atr_rank = _compute(library, "atr_percentile", panel, window=5, rank_window=6)
    assert np.isfinite(atr_rank.dropna().to_numpy()).all()
    assert (atr_rank.dropna() == 0.5).all().all()

    ratio = _compute(library, "intraday_to_close_vol_ratio", panel, window=5)
    assert not np.isinf(ratio.to_numpy(dtype=float, na_value=np.nan)).any()
    assert ratio.dropna().empty

    tail = _compute(library, "tail_loss_concentration", panel, window=5)
    assert np.isfinite(tail.dropna().to_numpy()).all()
    assert (tail.dropna() == 0.0).all().all()

    missing_close = flat.copy()
    missing_close.iloc[50, 0] = np.nan
    missing_panel = _panel(missing_close)
    for name in FACTOR_NAMES:
        result = _compute(library, name, missing_panel, **{
            "rank_window": 6,
        } if name == "atr_percentile" else {})
        assert not np.isinf(result.to_numpy(dtype=float, na_value=np.nan)).any()
        assert result.iloc[50].isna().any()


def test_window_and_tail_parameters_control_warmup_and_validation():
    panel = _sample_panel()
    loader = FactorLoader()
    library = loader.load()

    atr = _compute(library, "atr_percent", panel, window=3)
    assert atr.first_valid_index() == panel.close.index[3]
    rank = _compute(library, "atr_percentile", panel, window=3, rank_window=4)
    assert rank.first_valid_index() == panel.close.index[6]
    ratio = _compute(library, "intraday_to_close_vol_ratio", panel, window=3)
    assert ratio.first_valid_index() == panel.close.index[3]
    tail = _compute(library, "tail_loss_concentration", panel, window=3)
    assert tail.first_valid_index() == panel.close.index[3]

    for name in (
        "atr_percent",
        "atr_percentile",
        "intraday_to_close_vol_ratio",
        "tail_loss_concentration",
    ):
        with pytest.raises(ValueError):
            _compute(library, name, panel, window=1)
    with pytest.raises(ValueError):
        _compute(library, "atr_percentile", panel, window=3, rank_window=1)
    with pytest.raises(ValueError):
        _compute(library, "tail_loss_concentration", panel, tail_fraction=0.0)
    with pytest.raises(ValueError):
        _compute(library, "tail_loss_concentration", panel, tail_fraction=1.1)


def test_volatility_structure_factors_do_not_use_future_rows():
    panel = _sample_panel()
    changed_fields = {}
    for field in panel.fields:
        changed = panel[field].copy()
        changed.iloc[80:] = changed.iloc[80:] * 10.0
        changed_fields[field] = changed
    changed_panel = Panel(changed_fields)

    loader = FactorLoader()
    loader.load()
    for name in FACTOR_NAMES:
        baseline = loader.factors[name].compute(panel)
        changed = loader.factors[name].compute(changed_panel)
        pd.testing.assert_frame_equal(
            baseline.iloc[:80], changed.iloc[:80], check_exact=True
        )
