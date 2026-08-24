"""WorldQuant Alpha 101 因子库验证。"""

import numpy as np
import pandas as pd

from app.quantcore.factor.base import Panel, library_factors
from app import FactorLoader


def _panel(days: int = 300) -> Panel:
    dates = pd.bdate_range("2023-01-03", periods=days)
    symbols = ["A", "B", "C", "D"]
    t = np.arange(days, dtype=float)[:, None]
    offsets = np.arange(len(symbols), dtype=float)[None, :]
    close_values = 50.0 + 0.08 * t + offsets + 1.5 * np.sin(t / 11.0 + offsets)
    close = pd.DataFrame(close_values, index=dates, columns=symbols)
    open_ = close * (1.0 + 0.003 * np.cos(t / 7.0 + offsets))
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    volume = pd.DataFrame(
        1_000_000.0 * (1.0 + 0.08 * np.sin(t / 13.0 + offsets)),
        index=dates,
        columns=symbols,
    )
    amount = close * volume
    total_mv = close * volume * 100.0
    groups = pd.DataFrame(
        np.tile(["G1", "G1", "G2", "G2"], (days, 1)),
        index=dates,
        columns=symbols,
    )
    return Panel({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": amount,
        "total_mv": total_mv,
        "sector": groups,
        "industry": groups,
        "subindustry": groups,
    })


def test_worldquant_alpha101_library_registers_all_factors():
    library = FactorLoader().load("worldquant_alpha101")
    factors = library_factors(library)

    assert len(factors) == 101
    assert list(factors)[:2] == ["alpha001", "alpha002"]
    assert list(factors)[-2:] == ["alpha100", "alpha101"]


def test_worldquant_reference_formulae():
    loader = FactorLoader()
    loader.load("worldquant_alpha101")
    panel = _panel()

    expected_2 = -(
        np.log(panel.volume)
        .diff(2)
        .rank(axis=1, pct=True)
        .rolling(6, min_periods=6)
        .corr(((panel.close - panel.open) / panel.open).rank(axis=1, pct=True))
    )
    pd.testing.assert_frame_equal(
        loader.factors["alpha002"].compute(panel), expected_2
    )

    vwap = panel.amount / panel.volume
    expected_41 = np.sqrt(panel.high * panel.low) - vwap
    pd.testing.assert_frame_equal(
        loader.factors["alpha041"].compute(panel), expected_41
    )

    expected_101 = (panel.close - panel.open) / (panel.high - panel.low + 0.001)
    pd.testing.assert_frame_equal(
        loader.factors["alpha101"].compute(panel), expected_101
    )


def test_all_worldquant_alpha101_factors_compute_on_panel():
    loader = FactorLoader()
    loader.load("worldquant_alpha101")
    panel = _panel()

    for factor in loader.factors.values():
        result = factor.compute(panel)
        assert result.shape == panel.close.shape
        assert result.index.equals(panel.close.index)
        assert result.columns.equals(panel.close.columns)


def test_worldquant_factors_do_not_read_future_rows():
    loader = FactorLoader()
    loader.load("worldquant_alpha101")
    panel = _panel()
    changed = _panel()
    changed_close = changed.close.copy()
    changed_close.iloc[-1] *= 2.0
    changed._fields["close"] = changed_close

    cutoff = panel.close.index[-2]
    for name in ("alpha001", "alpha041", "alpha058", "alpha101"):
        before = loader.factors[name].compute(panel).loc[:cutoff]
        after = loader.factors[name].compute(changed).loc[:cutoff]
        pd.testing.assert_frame_equal(before, after)


def test_worldquant_vwap_fallback_works_without_amount():
    full = _panel()
    fields = {
        name: value
        for name, value in full._fields.items()
        if name not in {"amount", "total_mv", "sector", "industry", "subindustry"}
    }
    panel = Panel(fields)
    loader = FactorLoader()
    loader.load("worldquant_alpha101")

    result = loader.factors["alpha041"].compute(panel)
    expected = np.sqrt(panel.high * panel.low) - (
        panel.high + panel.low + panel.close
    ) / 3.0
    pd.testing.assert_frame_equal(result, expected)


def test_factor_api_lists_worldquant_alpha101():
    from app.api.routes import _builtin_factors

    names = {factor.name for factor in _builtin_factors()}
    assert "alpha001" in names
    assert "alpha101" in names


def test_builtin_runner_loads_worldquant_alpha101_factor():
    from app.services.factor.runner import _load_factor_from_builtin_library

    factor = _load_factor_from_builtin_library("worldquant_alpha101", "alpha101")
    assert factor.name == "alpha101"
