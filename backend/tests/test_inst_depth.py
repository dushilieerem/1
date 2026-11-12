# -*- coding: utf-8 -*-
"""M13：24 家公司研究深度的数据覆盖摘要。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.institution import depth  # noqa: E402
from services.marketdata import store as md  # noqa: E402


def test_market_coverage(monkeypatch) -> None:
    monkeypatch.setattr(md, "financials", lambda symbol, limit=8: [{"revenue": 1}] * 3)
    monkeypatch.setattr(md, "valuation_latest", lambda symbol: {"pe_ttm": 20.0})
    monkeypatch.setattr(md, "industry_latest", lambda symbol: {"industry_code": "S34"})
    out = depth.market_coverage("600519.SH")
    assert out == {
        "symbol": "600519.SH",
        "financials": 3,
        "valuation": True,
        "industry": True,
    }


def test_market_coverage_empty(monkeypatch) -> None:
    monkeypatch.setattr(md, "financials", lambda symbol, limit=8: [])
    monkeypatch.setattr(md, "valuation_latest", lambda symbol: None)
    monkeypatch.setattr(md, "industry_latest", lambda symbol: None)
    out = depth.market_coverage("AAPL.O")
    assert out["financials"] == 0 and out["valuation"] is False and out["industry"] is False
