# -*- coding: utf-8 -*-
"""P1-F01/F02：Brinson 归因与多因子合成。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factor.attribution import brinson_fachler, run_attribution  # noqa: E402
from services.factor.factor_combo import combine, zscore  # noqa: E402


def test_brinson_components_sum_to_total() -> None:
    groups = [
        {"name": "A", "portfolio_weight": 0.6, "benchmark_weight": 0.5, "portfolio_return": 0.10, "benchmark_return": 0.08},
        {"name": "B", "portfolio_weight": 0.4, "benchmark_weight": 0.5, "portfolio_return": 0.02, "benchmark_return": 0.04},
    ]
    out = brinson_fachler(groups, benchmark_return=0.06)
    for g in out["groups"]:
        assert abs(g["total"] - (g["allocation"] + g["selection"] + g["interaction"])) < 1e-12
    assert abs(out["total"] - sum(g["total"] for g in out["groups"])) < 1e-12
    assert out["top_contributors"]


def test_style_contribution() -> None:
    out = run_attribution(
        {
            "groups": [
                {"name": "A", "portfolio_weight": 1, "benchmark_weight": 1, "portfolio_return": 0.05, "benchmark_return": 0.05}
            ],
            "exposures": {"value": 0.5, "size": -0.2},
            "style_returns": {"value": 0.02, "size": 0.01},
        }
    )
    assert abs(out["style"]["total"] - (0.5 * 0.02 + -0.2 * 0.01)) < 1e-12


def test_brinson_rejects_missing_returns() -> None:
    with pytest.raises(ValueError):
        brinson_fachler([{"name": "A", "portfolio_weight": 1, "benchmark_weight": 1}])


def test_zscore_and_equal_weight_combo() -> None:
    factors = {"f1": [1.0, 2.0, 3.0], "f2": [3.0, 2.0, 1.0]}
    out = combine(factors=factors, scheme="equal")
    assert out["weights"] == {"f1": 0.5, "f2": 0.5}
    # 两个反向标准化因子等权后分数约为 0
    assert all(abs(x) < 1e-9 for x in out["scores"])
    assert zscore([1, 2, 3])[0] < 0 < zscore([1, 2, 3])[2]


def test_ic_weighting_and_timing() -> None:
    out = combine(
        factors={"f1": [1.0, 2.0, 3.0], "f2": [1.0, 5.0, 9.0]},
        scheme="ic",
        metrics={"f1": {"ic": 0.1}, "f2": {"ic": 0.3}},
        timing={"2026-01-01": 0.5, "2026-01-02": 0.0},
        dates=["2026-01-01", "2026-01-02", "2026-01-03"],
    )
    assert abs(out["weights"]["f1"] - 0.25) < 1e-9
    assert out["timing_multiplier"] == [0.5, 0.0, 1.0]
    assert out["timed_scores"][1] == 0.0


def test_combo_rejects_unknown_scheme() -> None:
    with pytest.raises(ValueError):
        combine(factors={"f1": [1, 2]}, scheme="magic")
