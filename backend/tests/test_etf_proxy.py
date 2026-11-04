# -*- coding: utf-8 -*-
"""H06/H07：ETF 跟踪指数与代理成分。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.invest import etf  # noqa: E402


def test_normalize_and_map() -> None:
    assert etf.normalize_etf("510300") == "510300.SH"
    assert etf.normalize_etf("159919") == "159919.SZ"
    assert etf.is_etf("510300.SH") is True
    assert etf.is_etf("600519.SH") is False
    with pytest.raises(ValueError):
        etf.normalize_etf("ABC")


def test_profile_unmapped() -> None:
    out = etf.profile("512990")
    assert out["tracking"] == "unmapped"
    assert out["tracked_index"] is None


def test_profile_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        etf,
        "load_weights",
        lambda index: [
            {"symbol": "600519.SH", "weight": 5.0},
            {"symbol": "000858.SZ", "weight": 3.0},
        ],
    )
    out = etf.profile("510300")
    assert out["tracking"] == "index_proxy"
    assert out["tracked_index"] == "000300.SH"
    assert out["constituent_count"] == 2


def test_overlap(monkeypatch) -> None:
    monkeypatch.setattr(
        etf,
        "load_weights",
        lambda index: (
            [{"symbol": "A", "weight": 5.0}, {"symbol": "B", "weight": 3.0}]
            if index == "000300.SH"
            else [{"symbol": "B", "weight": 4.0}, {"symbol": "C", "weight": 2.0}]
        ),
    )
    out = etf.overlap("510300", "510500")
    assert out["common_count"] == 1
    assert out["overlap_weight_pct"] == 3.0
