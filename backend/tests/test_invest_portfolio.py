# -*- coding: utf-8 -*-
"""组合页读模型：收益、归因、诊断、目标配置与净值曲线。"""
from __future__ import annotations

import pytest

from services.invest import rules


class FakeConn:
    def execute(self, sql, params=()):
        return self

    def fetchall(self):
        return []

    def fetchone(self):
        return None


def _holding(code, name, shares, cost, price, prev, industry, *, target=0.0, amount=3e9, pe=20.0):
    return {
        "code": code, "name": name, "shares": shares, "cost": cost,
        "target_weight": target, "industry": industry, "stock_industry": industry,
        "industry_name": industry, "industry_level": "1", "price": price, "prev_close": prev,
        "beta": 0.9, "asset": "stock", "stock_amount": amount, "pe_ttm": pe,
    }


@pytest.fixture
def holdings():
    return [
        _holding("600036", "招商银行", 4845, 35.0, 38.2, 37.75, "银行", amount=2e9, pe=6.0),
        _holding("300750", "宁德时代", 894, 260.0, 252.0, 254.0, "新能源", amount=8e9, pe=30.0),
        _holding("600519", "贵州茅台", 116, 1500.0, 1620.0, 1596.0, "食品饮料", amount=3e9, pe=28.0),
        {**_holding("510300", "沪深300ETF", 46046, 3.75, 3.95, 3.935, "宽基", amount=5e9, pe=None),
         "asset": "etf", "beta": 1.0},
        {"code": "CASH", "name": None, "shares": 86400, "cost": 1.0, "target_weight": 0,
         "industry": "现金", "stock_industry": None, "industry_name": None,
         "industry_level": None, "price": None, "prev_close": None, "beta": None,
         "asset": None, "stock_amount": None, "pe_ttm": None},
    ]


@pytest.fixture
def fake_rules(monkeypatch, holdings):
    monkeypatch.setattr(rules, "portfolio_rows", lambda conn, uid: [dict(h) for h in holdings])
    monkeypatch.setattr(rules, "data_meta", lambda conn: {"dataDate": "2026-11-03", "dataSource": "test", "isDemo": False})
    monkeypatch.setattr(rules, "latest_date", lambda conn: "2026-11-03")
    monkeypatch.setattr(rules, "stock_bars", lambda conn, code, limit=750: [
        {"date": f"2026-01-{i:02d}", "close": 100 + i * 0.3} for i in range(1, 29)
    ])

    def one(conn, sql, args=()):
        if "portfolio_meta" in sql:
            return {"trade_cost_pct": 0.4, "annual_turnover": 35, "impact_cost_pct": 0.08}
        if "indices" in sql:
            return {"price": 4128.6, "prev_close": 4100.0}
        return None

    monkeypatch.setattr(rules, "one", one)


def test_portfolio_returns_and_attribution(fake_rules):
    out = rules.build_portfolio(FakeConn(), 1, include_penetration=False)

    assert out["totalValue"] == pytest.approx(866569, abs=1)
    assert out["totalCost"] == pytest.approx(835088, abs=1)
    assert out["totalPnlPct"] == pytest.approx(3.77, abs=0.02)
    assert out["dailyChange"] == pytest.approx(0.46, abs=0.01)
    assert out["attribution"]["total"] == pytest.approx(out["dailyChange"], abs=0.01)
    assert out["attribution"]["needReview"] is False
    assert "跑输沪深300" in out["attribution"]["summary"]

    cash = next(h for h in out["holdings"] if h["isCash"])
    assert cash["todayPct"] is None and cash["pnlPct"] is None


def test_portfolio_diagnosis_sorted_and_capped(fake_rules):
    out = rules.build_portfolio(FakeConn(), 1, include_penetration=False)
    levels = [d["level"] for d in out["diagnosis"]]
    assert levels == sorted(levels, key=lambda x: 0 if x == "high" else 1)
    assert len(out["diagnosis"]) <= 5
    assert all(d["value"] > d["threshold"] for d in out["diagnosis"])


def test_portfolio_targets_not_auto_filled(fake_rules):
    out = rules.build_portfolio(FakeConn(), 1, include_penetration=False)
    assert out["targetConfigured"] is False
    assert out["deviation"] == []


def test_portfolio_stress_marks_no_exposure(monkeypatch, fake_rules):
    monkeypatch.setattr(rules, "portfolio_rows", lambda conn, uid: [
        _holding("600036", "招商银行", 100, 30.0, 38.0, 37.8, "银行", amount=2e9),
    ])
    out = rules.build_portfolio(FakeConn(), 1, include_penetration=False)
    by_key = {s["key"]: s for s in out["stress"]}
    assert by_key["newenergy"]["value"] is None
    assert by_key["consumer"]["value"] is None
    assert by_key["market"]["value"] < 0


def test_portfolio_nav_starts_at_zero(monkeypatch, fake_rules):
    monkeypatch.setattr(rules, "_index_bars", lambda conn, limit: [
        {"date": f"2026-01-{i:02d}", "close": 4000 + i} for i in range(1, 25)
    ])
    out = rules.portfolio_nav(FakeConn(), 1, "1m")
    assert out["dates"]
    assert out["portfolio"][0] == pytest.approx(0.0, abs=0.01)
    assert out["benchmark"][0] == pytest.approx(0.0, abs=0.01)
    assert len(out["portfolio"]) == len(out["dates"]) == len(out["benchmark"])
