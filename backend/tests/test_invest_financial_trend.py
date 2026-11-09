# -*- coding: utf-8 -*-
"""H5 财务趋势：同类型报告期跨年、累计口径与同比。"""
from __future__ import annotations

from services.invest import rules


def test_financial_trend_groups_report_types_and_computes_yoy(monkeypatch):
    fake_rows = [
        {"report_date": "2024-09-30", "revenue": 100e8, "net_profit": 20e8, "eps": 1.0,
         "deducted_net_profit": None, "gross_margin": 0.3, "net_margin": 0.1, "roe": 0.1,
         "revenue_yoy": 0.1, "profit_yoy": 0.2, "operating_cf": 15e8},
        {"report_date": "2025-09-30", "revenue": 120e8, "net_profit": 24e8, "eps": 1.2,
         "deducted_net_profit": None, "gross_margin": 0.32, "net_margin": 0.11, "roe": 0.11,
         "revenue_yoy": 0.2, "profit_yoy": 0.2, "operating_cf": 18e8},
        {"report_date": "2024-12-31", "revenue": 180e8, "net_profit": 30e8, "eps": 1.5,
         "deducted_net_profit": None, "gross_margin": 0.3, "net_margin": 0.1, "roe": 0.15,
         "revenue_yoy": 0.1, "profit_yoy": 0.1, "operating_cf": 25e8},
        {"report_date": "2025-12-31", "revenue": 200e8, "net_profit": 36e8, "eps": 1.8,
         "deducted_net_profit": None, "gross_margin": 0.31, "net_margin": 0.12, "roe": 0.16,
         "revenue_yoy": 0.11, "profit_yoy": 0.2, "operating_cf": 30e8},
    ]
    monkeypatch.setattr(rules, "rows", lambda conn, sql, args=(): fake_rows)
    out = rules._financial_trend(object(), "600519")
    assert out["available"] is True
    by_label = {x["label"]: x for x in out["items"]}
    assert by_label["2025Q3"]["revenue"] == 120
    assert by_label["2025Q3"]["gross_margin"] == 32
    assert by_label["2025Q3"]["eps_yoy"] == 20
    assert by_label["2025年报"]["operating_cf_yoy"] == 20
