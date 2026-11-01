# -*- coding: utf-8 -*-
"""FR-RES-19..22：DCF 与敏感性表。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.institution.valuation import run_dcf  # noqa: E402


def _payload(**kw):
    base = {
        "base_revenue": 100.0,
        "revenue_growth": 0.10,
        "cashflow_margin": 0.30,
        "discount_rate": 0.10,
        "terminal_growth": 0.02,
        "years": 5,
        "shares_outstanding": 10.0,
    }
    base.update(kw)
    return base


def test_dcf_range_and_sensitivity() -> None:
    out = run_dcf(_payload())
    assert out["ok"] is True
    assert out["range"]["low"] < out["range"]["base"] < out["range"]["high"]
    assert out["range"]["base_per_share"] == pytest.approx(out["range"]["base"] / 10, rel=0.01)
    assert len(out["sensitivity"]["rows"]) == 3
    assert all(len(r["values"]) == 3 for r in out["sensitivity"]["rows"])


def test_discount_must_exceed_terminal() -> None:
    with pytest.raises(ValueError):
        run_dcf(_payload(discount_rate=0.04, terminal_growth=0.05))


def test_parameter_ranges() -> None:
    for bad in (
        {"revenue_growth": 0.30},
        {"cashflow_margin": 0.10},
        {"discount_rate": 0.20},
        {"terminal_growth": 0.10},
    ):
        with pytest.raises(ValueError):
            run_dcf(_payload(**bad))
