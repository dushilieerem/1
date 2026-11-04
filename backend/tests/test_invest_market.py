# -*- coding: utf-8 -*-
"""H5 中英文/中美市场切换：市场过滤、美股首页、搜索与个股本地化。"""
from __future__ import annotations

import pytest

from services.invest import rules


class FakeConn:
    def execute(self, sql, params=()):
        return self

    def fetchall(self):
        return []

    def fetchone(self):
        return {"d": "2026-10-29"}


def _us(code, name, price, prev, amount=1e9, pe=None):
    return {
        "code": code, "name": name, "industry": "未分类", "asset": "stock",
        "price": price, "prev_close": prev, "open": price, "high": price, "low": price,
        "amount": amount, "pe_ttm": pe,
        "market_cap": None, "beta": None, "dividend_yield": None, "pb": None,
        "turnover": None, "volume": None, "updated_at": "2026-10-29",
        "next_report_date": None, "pinyin": None,
    }


def test_market_helpers():
    assert rules._market_sql("US") == "market='US'"
    assert rules._market_sql("CN") == "COALESCE(market,'CN')='CN'"
    assert rules._display_name({"code": "AAPL.O", "name": "苹果"}, "US") == "Apple"
    assert rules._display_name({"code": "600519", "name": "贵州茅台"}, "CN") == "贵州茅台"
    assert rules._display_industry({"code": "AAPL.O", "industry": "未分类"}, "US") == "US equity"


def test_us_home_breadth(monkeypatch):
    stocks = [
        _us("AAPL.O", "苹果", 110, 100, amount=5e9),
        _us("MSFT.O", "微软", 90, 100, amount=4e9),
        _us("NVDA.O", "英伟达", 120, 100, amount=3e9),
    ]
    monkeypatch.setattr(rules, "rows", lambda conn, sql, args=(): (
        stocks if "FROM stocks" in sql else []
    ))
    out = rules.build_home(conn=FakeConn(), user_id=1, market="US")
    assert out["market"] == "US"
    assert out["coverage"]["quotes"] is True and out["coverage"]["news"] is False
    assert out["indices"] == [] and out["topics"] == []
    assert "advancers" in out["review"]["summary"]
    assert out["daily"][0]["tag"].startswith("US")


def test_us_home_without_coverage(monkeypatch):
    monkeypatch.setattr(rules, "rows", lambda conn, sql, args=(): [])
    out = rules.build_home(conn=FakeConn(), user_id=1, market="US")
    assert out["market"] == "US" and out["hasQuotes"] is False
    assert out["coverage"]["quotes"] is False and out["coverage"]["fundamentals"] is False
    assert out["daily"] == []
    assert "unavailable" in out["review"]["title"].lower()
    assert out["watchlist"] == []


def test_us_search_presets(monkeypatch):
    stocks = [
        _us("AAPL.O", "苹果", 110, 100, amount=5e9),
        _us("MSFT.O", "微软", 90, 100, amount=4e9),
        _us("NVDA.O", "英伟达", 120, 100, amount=3e9),
    ]
    monkeypatch.setattr(rules, "rows", lambda conn, sql, args=(): stocks if "FROM stocks" in sql else [])
    out = rules.build_search(FakeConn(), "", "US")
    assert out["market"] == "US"
    assert {p["key"] for p in out["presets"]} == {"active", "gainers", "majors"}
    assert out["presets"][0]["items"][0]["name"] == "Apple"
    by_q = rules.build_search(FakeConn(), "AAPL", "US")
    assert by_q["results"][0]["id"] == "AAPL.O"
    assert by_q["results"][0]["name"] == "Apple"


def test_us_watchlist_filters_market(monkeypatch):
    def fake_rows(conn, sql, args=()):
        if "FROM watchlist" in sql:
            return [{"code": "AAPL.O", "group_name": "Default"}]
        return []

    monkeypatch.setattr(rules, "rows", fake_rows)
    def one(conn, sql, args=()):
        if "FROM stocks" in sql and "code=?" in sql:
            if args and args[0] == "AAPL.O":
                return _us("AAPL.O", "苹果", 110, 100)
            return None
        return None
    monkeypatch.setattr(rules, "one", one)
    out = rules.build_watchlist(FakeConn(), 1, "US")
    assert out["market"] == "US"
    assert out["groups"][0]["items"][0]["name"] == "Apple"
    assert out["groups"][0]["items"][0]["industry"] == "US equity"
    assert "no real-time push" in out["disclaimer"]


def test_us_stock_is_localized(monkeypatch):
    stock = _us("AAPL.O", "苹果", 110, 100)
    monkeypatch.setattr(rules, "one", lambda conn, sql, args=(): stock if "FROM stocks" in sql and "code=?" in sql else None)
    monkeypatch.setattr(rules, "rows", lambda conn, sql, args=(): [])
    monkeypatch.setattr(rules, "stock_bars", lambda conn, code, limit=750: [
        {"date": f"2026-10-{i:02d}", "open": 100 + i, "high": 101 + i, "low": 99 + i,
         "close": 100 + i, "volume": 1000} for i in range(1, 29)
    ])
    out = rules.build_stock(FakeConn(), "AAPL.O")
    assert out["quote"]["name"] == "Apple"
    assert out["quote"]["industry"] == "US equity"
    assert out["financials"] == [] and out["news"] == []
    assert out["valuation"]["label"] == "No valuation data"
    assert out["dataSource"] == "Public EOD (US)"
    assert out["coverage"]["valuation"] is False
    assert all(ord(ch) < 128 for ch in " ".join(out["summary"]))


def test_cn_stock_beta_falls_back_to_risk_daily(monkeypatch):
    stock = {
        "code": "600519", "name": "贵州茅台", "industry": "食品饮料", "asset": "stock",
        "price": 1480.0, "prev_close": 1439.1, "open": 1450.0, "high": 1480.0, "low": 1435.0,
        "market_cap": 18500.0, "pe_ttm": 22.5, "pb": 6.8, "dividend_yield": 1.9,
        "turnover": 0.6, "volume": 1000, "amount": 1e9, "beta": None,
        "updated_at": "2026-11-03", "next_report_date": None, "pinyin": None,
    }

    def one(conn, sql, args=()):
        if "FROM stocks" in sql and "code=?" in sql:
            return stock
        if "md_risk_daily" in sql:
            return {"beta_1y": 1.23}
        return None

    monkeypatch.setattr(rules, "one", one)
    monkeypatch.setattr(rules, "rows", lambda conn, sql, args=(): [])
    monkeypatch.setattr(rules, "data_meta", lambda conn: {"dataDate": "2026-11-03", "dataSource": "test", "isDemo": False})
    monkeypatch.setattr(rules, "latest_date", lambda conn: "2026-11-03")
    monkeypatch.setattr(rules, "stock_bars", lambda conn, code, limit=750: [
        {"date": f"2026-09-{i:02d}", "open": 100 + i, "high": 101 + i, "low": 99 + i,
         "close": 100 + i, "volume": 1000} for i in range(1, 29)
    ])
    out = rules.build_stock(FakeConn(), "600519")
    assert out["quote"]["beta"] == 1.23
    assert out["quote"]["nextReportDateAvailable"] is False
