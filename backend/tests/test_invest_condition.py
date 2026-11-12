# -*- coding: utf-8 -*-
"""H5 条件选股：六条预设解析、异常分支与筛选边界。"""
from __future__ import annotations

from services.invest import condition


PRESETS = [
    "PE 分位低于 30%，近 3 年净利润连续增长，ROE 大于 10%",
    "股息率大于 3%，PE 分位低于 30%，近 1 年最大回撤小于 25%",
    "总市值小于 200 亿，近 20 日涨幅大于 10%，近 5 日主力净流入大于 5000 万",
    "近 5 日主力净流入合计大于 5000 万，且连续 3 日为正",
    "收盘价创 60 日新高，成交量大于 5 日均量 1.5 倍，且站上 60 日均线",
    "较 60 日高点回撤大于 25%，近 3 日连续收阳，成交额较前 5 日放大",
]


def test_six_presets_parse_exact_conditions():
    expected = [
        [("pe_percentile", "max", 30), ("profit_growth_years", "bool", 3), ("roe", "min", 10)],
        [("dividend_yield", "min", 3), ("pe_percentile", "max", 30), ("max_drawdown_1y", "max", 25)],
        [("market_cap", "max", 200), ("return_20d", "min", 10), ("main_net_inflow_5d", "min", 5000)],
        [("main_net_inflow_5d", "min", 5000), ("main_inflow_days", "min", 3)],
        [("high_60d", "bool", 60), ("volume_ratio_5d", "min", 1.5), ("above_ma60", "bool", 60)],
        [("drawdown_60d_high", "min", 25), ("up_days_3", "bool", 3), ("volume_expand_5d", "bool", 5)],
    ]
    for query, rows in zip(PRESETS, expected):
        parsed = condition.parse_query(query)
        got = [(c["key"], c["op"], c["value"]) for c in parsed["conditions"]]
        assert got == rows, query
        assert not parsed["unrecognized"], query
        assert not parsed["conflicts"], query


def test_fund_flow_presets_are_supported():
    for query in (PRESETS[2], PRESETS[3]):
        parsed = condition.parse_query(query)
        assert parsed["all_recognized"] is True
        assert not parsed["unsupported"]
        assert {c["key"] for c in parsed["conditions"]} >= {"main_net_inflow_5d"}


def test_partial_recognition_gives_two_alternatives():
    parsed = condition.parse_query("PE 分位低于 30%，最近很热的股票")
    assert [c["key"] for c in parsed["conditions"]] == ["pe_percentile"]
    assert len(parsed["unrecognized"]) == 1
    assert len(parsed["unrecognized"][0]["suggestions"]) == 2
    assert parsed["all_recognized"] is False


def test_conflict_blocks_execution():
    parsed = condition.parse_query("PE 分位低于 30% 且 PE 分位高于 70%")
    assert len(parsed["conditions"]) == 2
    assert parsed["conflicts"]
    assert parsed["all_recognized"] is False


def test_normalize_conditions_roundtrip_keeps_fund_flow():
    parsed = condition.parse_query(PRESETS[2])
    kept = condition.normalize_conditions(parsed["conditions"])
    assert [c["key"] for c in kept] == ["market_cap", "return_20d", "main_net_inflow_5d"]
    assert all(c["supported"] for c in kept)


def test_fund_flow_candidate_is_converted_to_wan_and_days(monkeypatch):
    monkeypatch.setattr(
        condition.rules, "rows",
        lambda *args, **kwargs: [{
            "symbol": "600519.SH", "main_net_inflow_5d": 85_550_000.0,
            "consecutive_inflow_days": 4,
        }],
    )
    out = condition._load_fund_flow(object(), ["600519"])
    assert out["600519"]["main_net_inflow_5d"] == 8555.0
    assert out["600519"]["main_inflow_days"] == 4


def test_roe_is_normalized_to_percent(monkeypatch):
    monkeypatch.setattr(
        condition.rules, "rows",
        lambda *args, **kwargs: [{"symbol": "600519.SH", "roe": 0.0522}],
    )
    assert condition._load_roe(object(), ["600519"], "2026-11-02") == {"600519": 5.22}


def _stock(code: str, cap: float, roe: float | None = None, industry: str = "食品饮料") -> dict:
    return {
        "code": code, "name": f"股票{code}", "industry": industry,
        "price": 10.0, "change_pct": 1.2, "market_cap": cap,
        "pe_ttm": 20.0, "dividend_yield": 2.0, "roe": roe,
    }


def _screen(monkeypatch, stocks, conditions):
    monkeypatch.setattr(condition.rules, "latest_date", lambda conn: "2026-11-02")
    monkeypatch.setattr(condition, "_base_candidates", lambda conn: stocks)
    return condition.screen_conditions(object(), conditions)


def test_screen_empty_points_to_blocking_condition_and_relax_options(monkeypatch):
    stocks = [_stock("600519", 300, roe=5.0), _stock("000001", 100, roe=6.0)]
    conditions = condition.parse_query("ROE 大于 10%")["conditions"]

    def fake_roe(conn, codes, data_date):
        return {c: 5.0 for c in codes}

    monkeypatch.setattr(condition, "_load_roe", fake_roe)
    result = _screen(monkeypatch, stocks, conditions)
    assert result["status"] == "empty"
    assert result["diagnostic"]["blocking"] == "ROE"
    assert len(result["diagnostic"]["relax_actions"]) == 3


def test_pe_condition_uses_pe_ttm_field(monkeypatch):
    stocks = [_stock("600519", 300), _stock("000001", 100)]
    stocks[0]["pe_ttm"] = 18.0
    stocks[1]["pe_ttm"] = 35.0
    conditions = condition.parse_query("PE 小于 20 倍")["conditions"]
    result = _screen(monkeypatch, stocks, conditions)
    assert result["status"] == "ok"
    assert [i["code"] for i in result["items"]] == ["600519"]


def test_screen_too_broad_returns_suggestion(monkeypatch):
    stocks = [_stock(f"{i:06d}", 50.0) for i in range(201)]
    conditions = condition.parse_query("总市值小于 200 亿")["conditions"]
    result = _screen(monkeypatch, stocks, conditions)
    assert result["status"] == "too_broad"
    assert result["count"] == 201
    assert result["diagnostic"]["suggestion"]


def test_screen_ok_returns_max_five_plus_summary_and_industry(monkeypatch):
    stocks = [_stock("600519", 300), _stock("000001", 100, industry="银行"),
              _stock("300750", 50, industry="电力设备")]
    conditions = condition.parse_query("总市值小于 400 亿")["conditions"]
    result = _screen(monkeypatch, stocks, conditions)
    assert result["status"] == "ok"
    assert result["count"] == 3
    assert len(result["items"]) == 3
    assert result["summary"]
    assert 3 <= len(result["features"]) <= 4
    assert 1 <= len(result["risks"]) <= 3
    assert result["data_date"] == "2026-11-02"
    assert result["industry_distribution"][0]["name"] in {"食品饮料", "银行", "电力设备"}
    assert len(result["followups"]) == 3
