# -*- coding: utf-8 -*-
"""快速实验配置：因子权重与调仓频率。"""
from __future__ import annotations

import pytest

from services.invest import quant


def test_normalize_factors_keeps_custom_weights():
    out = quant._normalize_factors([
        {"key": "value", "direction": "low", "weight": 60},
        {"key": "momentum", "direction": "high", "weight": 40},
    ])
    assert [x["weight"] for x in out] == [60.0, 40.0]
    assert out[0]["direction"] == "low"


def test_normalize_factors_rejects_partial_weights():
    with pytest.raises(quant.QuantDataError):
        quant._normalize_factors([
            {"key": "value", "weight": 60},
            {"key": "momentum"},
        ])


def test_rebalance_groups_biweekly_and_quarterly():
    from datetime import date, timedelta

    start = date(2026, 1, 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(180)]
    panel = {"dates": dates}
    daily = quant._rebalance_groups(panel, 0, len(dates) - 1, "daily")
    weekly = quant._rebalance_groups(panel, 0, len(dates) - 1, "weekly")
    biweekly = quant._rebalance_groups(panel, 0, len(dates) - 1, "biweekly")
    monthly = quant._rebalance_groups(panel, 0, len(dates) - 1, "monthly")
    quarterly = quant._rebalance_groups(panel, 0, len(dates) - 1, "quarterly")
    assert len(daily) > len(weekly) > len(biweekly) > len(monthly) > len(quarterly)
    assert biweekly[0][0] == 0 and biweekly[-1][1] == len(dates) - 1
