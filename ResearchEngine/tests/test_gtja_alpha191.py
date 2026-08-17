"""国泰君安 Alpha191 因子库验证。"""

import numpy as np
import pandas as pd

from quantcore.factor.base import Panel, library_factors
from researchengine import FactorLoader


def _panel(days: int = 300, include_optional: bool = True) -> Panel:
    dates = pd.bdate_range("2023-01-03", periods=days)
    symbols = ["A", "B", "C", "D"]
    t = np.arange(days, dtype=float)[:, None]
    offsets = np.arange(len(symbols), dtype=float)[None, :]
    close = pd.DataFrame(
        50.0 + 0.08 * t + offsets + 1.5 * np.sin(t / 11.0 + offsets),
        index=dates,
        columns=symbols,
    )
    open_ = close * (1.0 + 0.003 * np.cos(t / 7.0 + offsets))
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    volume = pd.DataFrame(
        1_000_000.0 * (1.0 + 0.08 * np.sin(t / 13.0 + offsets)),
        index=dates,
        columns=symbols,
    )
    fields = {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
    if include_optional:
        fields["amount"] = close * volume
        fields["vwap"] = close * (1.0 + 0.001 * np.sin(t / 17.0 + offsets))
    return Panel(fields)


def test_gtja_alpha191_library_registers_all_factors():
    library = FactorLoader().load("gtja_alpha191")
    factors = library_factors(library)

    assert len(factors) == 191
    assert list(factors)[:2] == ["alpha191_001", "alpha191_002"]
    assert list(factors)[-2:] == ["alpha191_190", "alpha191_191"]


def test_gtja_reference_formulae():
    panel = _panel()
    library = FactorLoader().load("gtja_alpha191")
    factors = library_factors(library)

    expected_1 = -np.log(panel.volume).diff(1).rank(axis=1, pct=True).rolling(6).corr(
        ((panel.close - panel.open) / panel.open).rank(axis=1, pct=True)
    )
    pd.testing.assert_frame_equal(factors["alpha191_001"].compute(panel), expected_1)

    expected_2 = -(
        ((panel.close - panel.low) - (panel.high - panel.close))
        / (panel.high - panel.low)
    ).diff(1)
    pd.testing.assert_frame_equal(factors["alpha191_002"].compute(panel), expected_2)

    vwap = panel.vwap
    expected_41 = -(
        vwap.diff(3).rolling(5).max().rank(axis=1, pct=True)
    )
    pd.testing.assert_frame_equal(factors["alpha191_041"].compute(panel), expected_41)


def test_all_gtja_alpha191_factors_keep_panel_shape_and_no_infinity():
    panel = _panel()
    library = FactorLoader().load("gtja_alpha191")

    for factor in library_factors(library).values():
        result = factor.compute(panel)
        assert result.shape == panel.close.shape
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)
        assert not np.isinf(result.to_numpy(dtype=float)).any()


def test_gtja_vwap_fallback_without_amount_or_vwap():
    panel = _panel(include_optional=False)
    library = FactorLoader().load("gtja_alpha191")
    result = library_factors(library)["alpha191_041"].compute(panel)
    typical = (panel.high + panel.low + panel.close) / 3.0
    expected = -typical.diff(3).rolling(5).max().rank(axis=1, pct=True)

    pd.testing.assert_frame_equal(result, expected)


def test_gtja_factors_do_not_read_future_rows():
    panel = _panel()
    changed = _panel()
    changed_close = changed.close.copy()
    changed_close.iloc[-1] *= 2.0
    changed._fields["close"] = changed_close

    cutoff = panel.close.index[-2]
    library = FactorLoader().load("gtja_alpha191")
    factors = library_factors(library)
    for name in ("alpha191_001", "alpha191_041", "alpha191_149", "alpha191_191"):
        before = factors[name].compute(panel).loc[:cutoff]
        after = factors[name].compute(changed).loc[:cutoff]
        pd.testing.assert_frame_equal(before, after)
