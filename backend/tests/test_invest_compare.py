# -*- coding: utf-8 -*-
"""多标的对比 / 多空辩论：解析、维度与缺失值口径。"""
from __future__ import annotations

from services.invest import compare, debate, rules


class FakeConn:
    pass


def _stock(code: str, name: str, industry: str, *, revenue_yoy=10.0, pe=20.0, pe_pct=40.0) -> dict:
    return {
        "quote": {
            "code": code, "name": name, "industry": industry, "price": 100.0,
            "changePct": 1.2, "amount": 2e9, "turnover": 1.5, "dividendYield": 1.1,
        },
        "chart": {"bars": [{"close": 90 + i} for i in range(10)]},
        "technical": {"return20": 5.0, "drawdown": -8.0},
        "valuation": {"pe": pe, "pb": 3.0, "pePercentile": pe_pct},
        "report": {
            "revenue": 100.0, "revenueYoY": revenue_yoy,
            "netProfit": 12.0, "profitYoY": revenue_yoy - 2,
            "grossMargin": 35.0, "roe": 14.0,
        },
        "statements": {"cashflow": {"operating_cf": 3e9}},
        "fundFlow": {"twenty_day": 1.2},
        "risks": [{"title": "估值分位偏高", "detail": "当前 PE 较高", "level": "amber"}],
        "dataDate": "2026-11-06",
    }


def test_parse_compare_query_strips_intent_words():
    assert compare.parse_compare_query("宁德时代和比亚迪对比") == ["宁德时代", "比亚迪"]
    assert compare.parse_compare_query("对比宁德时代和比亚迪的估值与财务") == ["宁德时代", "比亚迪"]
    assert compare.parse_compare_query("宁德时代、比亚迪和贵州茅台对比") == ["宁德时代", "比亚迪", "贵州茅台"]
    assert compare.parse_compare_query("帮我比较 A 和 B 哪个好") == ["A", "B"]
    assert compare.parse_compare_query("对比数据港和光环新网") == ["数据港", "光环新网"]


def test_build_compare_dimensions_and_missing(monkeypatch):
    fixtures = {
        "300750": _stock("300750", "宁德时代", "电力设备", revenue_yoy=55.0, pe=13.3, pe_pct=20.0),
        "002594": _stock("002594", "比亚迪", "汽车", revenue_yoy=0.0, pe=24.5, pe_pct=60.0),
    }
    monkeypatch.setattr(rules, "build_stock", lambda conn, code, period="daily": fixtures.get(code))
    out = compare.build_compare(FakeConn(), ["300750", "002594"])
    keys = [d["key"] for d in out["dimensions"]]
    assert keys == ["market", "financial", "valuation"]
    assert all(item["name"] for item in out["items"])
    assert any("营收同比" in line["text"] for line in out["summary"])
    assert any("不同行业" in line["text"] for line in out["summary"])
    assert out["card"]["summary"] and out["disclaimer"]

    # 单边缺失：保留 None，由 UI 显示 —，不补造数值。
    fixtures["002594"]["valuation"]["pe"] = None
    monkeypatch.setattr(rules, "build_stock", lambda conn, code, period="daily": fixtures.get(code))
    out2 = compare.build_compare(FakeConn(), ["300750", "002594"])
    pe_row = next(r for r in out2["dimensions"][2]["rows"] if r["key"] == "pe")
    assert pe_row["values"][1] is None
    assert out2["dimensions"][2]["missing"][0]["name"] == "比亚迪"


def test_build_debate_has_both_sides_and_footer(monkeypatch):
    monkeypatch.setattr(rules, "build_stock", lambda conn, code, period="daily": _stock("300750", "宁德时代", "电力设备"))
    out = debate.build_debate(FakeConn(), "300750")
    assert out and out["bull"] and out["bear"]
    assert all(len(side) <= 4 for side in (out["bull"], out["bear"]))
    assert out["footer"] in out["card"]["disclaimer"]
    assert [s["title"] for s in out["card"]["sections"]] == ["利多", "利空"]
