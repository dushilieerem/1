# -*- coding: utf-8 -*-
"""C3：执行前校验与异常分类（不依赖券商的确定性部分）。"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.institution.execution_guard import evaluate, exception_types  # noqa: E402


def _eval(**kw):
    base = {
        "auth_status": "qualified",
        "valid_until": "2099-01-01",
        "direction": "buy",
        "price": 100.0,
        "price_low": 90.0,
        "price_high": 110.0,
        "cash": 1_000_000.0,
        "cost": 500_000.0,
        "qty": 5000,
        "position_qty": 0.0,
        "today": date(2026, 11, 1),
    }
    base.update(kw)
    return evaluate(**base)


def test_all_green() -> None:
    out = _eval()
    assert out["ok"] is True
    assert out["blocking"] == []


def test_suspended_or_st_blocks() -> None:
    out = _eval(suspended=True)
    assert out["ok"] is False
    assert "tradable" in out["blocking"]
    out = _eval(is_st=True)
    assert "tradable" in out["blocking"]


def test_price_range_and_expiry() -> None:
    out = _eval(price=120.0)
    assert "price_range" in out["blocking"]
    out = _eval(valid_until="2020-01-01")
    assert "validity" in out["blocking"]


def test_cash_and_position() -> None:
    out = _eval(cost=2_000_000.0)
    assert "cash" in out["blocking"]
    out = _eval(direction="sell", qty=5000, position_qty=1000, cost=0.0)
    assert "position" in out["blocking"]


def test_duplicate_order() -> None:
    out = _eval(duplicate_order=True)
    assert "duplicate" in out["blocking"]


def test_exception_type_mapping() -> None:
    assert exception_types(["cash", "tradable", "unknown"]) == [
        "cash_short",
        "suspended_or_st",
        "unknown",
    ]
