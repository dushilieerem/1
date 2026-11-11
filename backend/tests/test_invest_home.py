# -*- coding: utf-8 -*-
"""首页改版：三大指数、两市成交、今日概览三分组与热点风险标签。"""
from __future__ import annotations

from datetime import date

from services.invest import rules


def test_topic_risk_tags_always_have_at_least_one():
    assert rules._topic_risk_tags({"valuation_percentile": 88, "turnover_percentile": 50})[0]["label"] == "估值偏高"
    assert [t["label"] for t in rules._topic_risk_tags({"valuation_percentile": 42, "turnover_percentile": 81})] == ["估值分位 42%", "拥挤度高"]
    tags = rules._topic_risk_tags({"valuation_percentile": 42, "turnover_percentile": 38})
    assert len(tags) == 1 and tags[0]["label"] == "估值分位 42%"
    for t in tags:
        assert t["tone"] in {"red", "amber", "gray"}


def test_home_market_uses_required_indices_and_turnover(monkeypatch):
    quotes = {
        "000001.SH": (3345.67, 3330.0),
        "399001.SZ": (10876.54, 10840.0),
        "399006.SZ": (2214.80, 2190.0),
    }

    def fake_rows(conn, sql, args=()):
        if "md_index_bar" in sql:
            high, low = quotes[args[0]]
            return [
                {"trade_date": date(2026, 11, 4), "close": high},
                {"trade_date": date(2026, 11, 3), "close": low},
            ]
        return []

    def fake_one(conn, sql, args=()):
        if "md_index_bar" in sql and "SUM(amount)" in sql:
            return {"amt": 1_602_910_000_000.0 if str(args[0]).startswith("2026-11-03") else 1_702_910_000_000.0, "n": 2}
        if "md_index_bar" in sql and "MAX(trade_date)" in sql:
            return {"d": date(2026, 11, 3)}
        return None

    monkeypatch.setattr(rules, "rows", fake_rows)
    monkeypatch.setattr(rules, "one", fake_one)
    market = rules._home_market(object(), "2026-11-04")
    assert [i["available"] for i in market["indices"]] == [True, True, True]
    assert market["turnover"]["available"] is True
    assert market["turnover"]["value"] == 17029.1
    assert market["turnover"]["change"] > 0
    assert market["turnover"]["basis"] == "index"
    assert "指数口径" in market["turnover"]["basisLabel"]


def test_home_market_marks_missing_indices_without_proxy(monkeypatch):
    monkeypatch.setattr(rules, "rows", lambda conn, sql, args=(): [])
    monkeypatch.setattr(rules, "one", lambda conn, sql, args=(): None)
    market = rules._home_market(object(), "2026-11-04")
    assert [i["available"] for i in market["indices"]] == [False, False, False]
    assert market["turnover"]["available"] is False


def test_home_daily_has_stock_portfolio_market_sources():
    by_code = {
        "300750": {"code": "300750", "name": "宁德时代", "price": 100.0, "prev_close": 98.0,
                    "next_report_date": "2026-11-08"},
        "600519": {"code": "600519", "name": "贵州茅台", "price": 1439.1, "prev_close": 1420.0,
                    "next_report_date": None},
    }
    pf = {
        "holdings": [{"code": "300750"}],
        "diagnosis": [{"title": "行业集中度偏高", "evidence": "新能源合计 42.0%（阈值 40%）", "excess": 2.0}],
        "deviation": [],
    }
    market = {"turnover": {"available": True, "value": 17029.1, "change": -4.5}}
    daily = rules._home_daily(None, 1, "2026-11-04", pf, market, by_code, {"300750", "600519"})
    assert [d["source"] for d in daily] == ["stock", "portfolio", "market"]
    assert all(len(d["detail"]) <= 40 for d in daily)
    assert "2026-11-08" in daily[0]["title"] or "11-08" in daily[0]["title"]
    assert "42.0" in daily[1]["detail"]


def test_home_review_line_keeps_portfolio_number(monkeypatch):
    monkeypatch.setattr(
        rules, "one",
        lambda conn, sql, args=(): {"price": 4008.87, "prev_close": 4016.92},
    )
    line = rules._home_review_line(
        object(), {"holdings": [{"code": "300750"}], "dailyChange": 0.86},
        {"turnover": {"available": True, "value": 17029.1, "change": -4.5}},
    )
    assert "沪深300" in line and "组合" in line and len(line) <= 30


def test_ttm_revenue_uses_prior_annual_and_same_period():
    fins = [
        {"report_date": "2025-06-30", "revenue": 400},
        {"report_date": "2025-12-31", "revenue": 1000},
        {"report_date": "2026-06-30", "revenue": 500},
    ]
    assert rules._ttm_revenue_yi(fins) == 1100


def test_institutional_view_uses_research_ratings(monkeypatch):
    monkeypatch.setattr(
        rules, "rows",
        lambda conn, sql, args=(): [
            {"org_name": "机构A", "rating": "买入", "n": 2, "latest": "2026-11-04"},
            {"org_name": "机构B", "rating": "增持", "n": 1, "latest": "2026-11-03"},
        ],
    )
    out = rules._institutional_view(object(), "600519")
    assert out["available"] is True
    assert out["coverage"] == 2
    assert out["reportCount"] == 3
    assert out["ratings"][0] == {"label": "买入", "count": 2}
    assert out["target"] is None


def test_industry_heat_uses_turnover_change_flow_and_news():
    stocks = [
        {"industry": "电子", "price": 11, "prev_close": 10, "amount": 1e10},
        {"industry": "电子", "price": 22, "prev_close": 20, "amount": 1e10},
        {"industry": "银行", "price": 10.1, "prev_close": 10, "amount": 1e9},
    ]
    out = rules._industry_heat(
        stocks,
        [{"name": "电子", "value": 5.0}, {"name": "银行", "value": -2.0}],
        {"电子": 10, "银行": 1},
        limit=2,
    )
    assert [x["name"] for x in out] == ["电子", "银行"]
    assert out[0]["heat"] > out[1]["heat"]
    assert out[0]["fundFlow"] == 5.0
    assert out[0]["detailAvailable"] is True


def test_build_topics_returns_risk_tags_and_spark(monkeypatch):
    topics = [
        {"id": "ai", "name": "AI 算力", "summary": "热度", "heat": 86,
         "valuation_percentile": 88, "turnover_percentile": 72},
        {"id": "dividend", "name": "高股息", "summary": "分红", "heat": 64,
         "valuation_percentile": 42, "turnover_percentile": 38},
    ]

    def fake_rows(conn, sql, args=()):
        if "FROM topics" in sql:
            return topics
        if "FROM topic_bars" in sql:
            return [{"close": 10}, {"close": 11}]
        return []

    monkeypatch.setattr(rules, "rows", fake_rows)
    monkeypatch.setattr(rules, "latest_date", lambda conn: "2026-11-04")
    monkeypatch.setattr(rules, "_topic_detail_available", lambda conn, topic_id: False)
    out = rules.build_topics(object())
    assert len(out["items"]) == 2
    assert out["items"][0]["riskTags"][0]["label"] == "估值偏高"
    assert out["items"][1]["riskTags"][0]["label"] == "估值分位 42%"
    assert out["items"][0]["spark"] == [11, 10]
    assert out["items"][0]["detailAvailable"] is False
