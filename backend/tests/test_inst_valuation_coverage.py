# -*- coding: utf-8 -*-
"""估值覆盖：股本优先级、可信股本放宽 sanity、相对估值兜底。"""
from __future__ import annotations

from services.institution import research_service as svc


def test_valuation_share_count_prefers_pit_share_capital() -> None:
    shares, source = svc._valuation_share_count(
        {"total_shares": None, "total_mv": 289_596_467_440.0, "float_mv": 21_542_807_520.0},
        716.0,
        [
            {"effective_date": "2025-01-01", "announce_date": "2024-12-31", "total_shares": 100.0},
            {"effective_date": "2026-08-19", "announce_date": "2026-08-18", "total_shares": 404_464_340.0},
        ],
        "2026-11-10",
    )
    assert source == "share_capital"
    assert shares == 404_464_340.0


def test_valuation_share_count_falls_back_to_total_mv() -> None:
    shares, source = svc._valuation_share_count(
        {"total_shares": None, "total_mv": 716.0 * 1000, "float_mv": 716.0 * 100},
        716.0,
        [],
        "2026-11-10",
    )
    assert source == "total_mv/price"
    assert shares == 1000


def test_trusted_shares_allow_extreme_ratio() -> None:
    assert svc._valuation_usable(7.2, 716.0, "share_capital") is True
    assert svc._valuation_usable(7.2, 716.0, "float_mv/price") is False


def test_relative_pb_fallback_when_dcf_unavailable() -> None:
    out = svc._relative_valuation(
        {"total_equity": 2_880_000_000.0, "net_profit": -100.0},
        {"pb_median": 5.33, "pe_median": 20.0},
        404_464_340.0,
        716.0,
        "share_capital",
        prefer_pb=True,
    )
    assert out is not None
    assert out["method"] == "relative_pb"
    assert out["base"] > 0
    assert out["shares_source"] == "share_capital"


def test_relative_ps_fallback_for_loss_making_company() -> None:
    out = svc._relative_valuation(
        {
            "revenue": 1_000_000_000.0,
            "report_date": "2026-12-31",
            "net_profit": -50_000_000.0,
            "total_equity": -10_000_000.0,
        },
        {"pb_median": None, "pe_median": None, "ps_median": 2.0},
        100_000_000.0,
        30.0,
        "share_capital",
    )
    assert out is not None
    assert out["method"] == "relative_ps"
    assert out["base"] == 20.0
