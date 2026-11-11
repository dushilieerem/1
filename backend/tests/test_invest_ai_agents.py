# -*- coding: utf-8 -*-
"""H5 AI 卡片归一化、落盘缓存与 Agent 注册表。"""
from __future__ import annotations

import json

import pytest
from ai.errors import AiBadOutput
from ai.router.specs import TaskRequest
from ai.router.tasks.invest import validate_daily_review, validate_portfolio_risk, validate_stock_deep, validate_stock_diagnosis
from app.routers import invest_ai
from app.routers.invest_ai import _compact_result, _extract_compare_pair
from services.invest import agent_prompts, ai_cache


def test_compact_card_keeps_full_summary():
    out = _compact_result({
        "card": {
            "summary": "很" * 80,
            "sections": [{"title": "长文", "body": "很" * 200}],
            "disclaimer": "AI 生成 · 非投资建议",
        }
    })
    assert len(out["card"]["summary"]) == 80
    assert out["card"]["sections"] == []
    assert out["card"]["disclaimer"]


def test_compact_card_falls_back_to_section_body():
    out = _compact_result({"card": {"summary": "", "sections": [{"body": "估值偏高，先看盈利。"}]}})
    assert out["card"]["summary"] == "估值偏高，先看盈利。"


def test_compact_deep_card_keeps_five_dimensions():
    sections = [
        {"key": "fundamental", "title": "基本面", "body": "营收增长。", "items": [{"k": "营收", "v": "100 亿"}]},
        {"key": "profitability", "title": "盈利", "body": "毛利率稳定。"},
        {"key": "valuation", "title": "估值", "body": "PE 中位。"},
        {"key": "risk", "title": "风险", "body": "估值分位偏高。"},
        {"key": "capital", "title": "资金", "body": "主力净流入。"},
    ]
    out = _compact_result({"card": {"summary": "总体平稳。", "sections": sections}}, keep_sections=True)
    assert [s["key"] for s in out["card"]["sections"]] == [
        "fundamental", "profitability", "valuation", "risk", "capital",
    ]
    assert out["card"]["sections"][0]["items"][0]["v"] == "100 亿"


def test_stock_deep_validator_requires_all_five_dimensions():
    raw = json.dumps({
        "summary": "总体平稳。",
        "sections": [{"key": "fundamental", "title": "基本面", "body": "有数据。"}],
    })
    with pytest.raises(AiBadOutput):
        validate_stock_deep(raw, TaskRequest())


def test_stock_deep_validator_accepts_section_blocks():
    sections = [
        {
            "key": key,
            "title": key,
            "blocks": [
                {"type": "paragraph", "text": f"{key} 的两到四句分析。"},
                {"type": "bullets", "items": ["并列要点一", "并列要点二"]},
            ],
        }
        for key in ("fundamental", "profitability", "valuation", "risk", "capital")
    ]
    out = validate_stock_deep(json.dumps({"summary": "总体平稳。", "sections": sections}), TaskRequest())
    assert out["sections"][0]["body"] == "fundamental 的两到四句分析。"
    assert out["sections"][0]["blocks"][0]["type"] == "paragraph"
    assert out["sections"][0]["blocks"][1]["items"] == ["并列要点一", "并列要点二"]
    kept = _compact_result({"card": out}, keep_sections=True)
    assert kept["card"]["sections"][0]["blocks"][1]["items"][0] == "并列要点一"


def test_stock_deep_validator_normalizes_five_dimensions():
    sections = [
        {"key": key, "title": "模型乱写的标题", "body": f"{key} 的事实。", "items": [{"k": "指标", "v": "1"}]}
        for key in ("capital", "risk", "valuation", "profitability", "fundamental")
    ]
    out = validate_stock_deep(json.dumps({"summary": "总体平稳。", "sections": sections}), TaskRequest())
    assert [s["title"] for s in out["sections"]] == ["基本面", "盈利", "估值", "风险", "资金"]


def test_portfolio_risk_validator_requires_six_sections():
    keys = ("score", "structure", "today", "stress", "deviation", "limits")
    sections = [{"key": key, "blocks": [{"type": "bullets", "items": [f"{key} 要点"]}]} for key in keys]
    out = validate_portfolio_risk(json.dumps({"summary": "风险分 50", "sections": sections}), TaskRequest())
    assert [s["key"] for s in out["sections"]] == list(keys)


def test_portfolio_risk_default_has_tables_and_charts():
    portfolio = {
        "riskScore": 62, "riskLabel": "较集中", "kpis": [{"label": "总资产", "value": "100 万"}],
        "diagnosis": [{"id": "single", "title": "单票集中", "value": 35, "threshold": 30, "excess": 5, "impact": "波动放大"}],
        "riskMethod": {"items": [{"key": "industry", "label": "行业集中", "available": True, "detail": "前两大行业 30%"}]},
        "attribution": {"items": [{"name": "测试", "contributionPct": 0.8}], "benchmark": {"changePct": 0.2}},
        "dailyChange": 1.0, "stress": [{"name": "沪深 300 −10%", "value": -8.0}],
        "deviation": [{"name": "测试", "target": 10, "current": 12, "diff": 2, "status": "超配"}],
        "penetration": {"coveragePct": 80},
    }
    card, charts = invest_ai._portfolio_risk_default(portfolio)
    assert [s["key"] for s in card["sections"]] == ["score", "structure", "today", "stress", "deviation", "limits"]
    assert any(b.get("type") == "table" for s in card["sections"] for b in s["blocks"])
    assert len(charts) == 2
    assert "风险分" in card["summary"]


def test_daily_review_validator_requires_three_core_sections():
    sections = [
        {"key": key, "blocks": [{"type": "bullets", "items": [f"{key} 要点"]}]}
        for key in ("market", "structure", "portfolio")
    ]
    out = validate_daily_review(json.dumps({"summary": "今日震荡", "sections": sections}), TaskRequest())
    assert [s["key"] for s in out["sections"]] == ["market", "structure", "portfolio"]
    with pytest.raises(AiBadOutput):
        validate_daily_review(json.dumps({"summary": "缺结构", "sections": sections[:2]}), TaskRequest())


def test_daily_review_default_has_market_portfolio_and_charts():
    home = {
        "marketPulse": {
            "indices": [{"label": "上证指数", "available": True, "change": 0.5}],
            "turnover": {"available": True, "value": 10000, "change": 5},
            "breadth": {"available": True, "advancers": 3000, "decliners": 2000, "limitUp": 50, "limitDown": 10},
            "sectors": {"leaders": [{"name": "新能源"}], "laggards": [{"name": "银行"}]},
        },
        "review": {"summary": "成交放量，新能源领涨。"},
        "topics": [{"name": "新能源"}], "daily": [{"title": "自选异动", "detail": "上涨 3%"}],
    }
    portfolio = {
        "holdings": [{"name": "测试"}], "dailyChange": 1.0,
        "attribution": {"items": [{"name": "测试", "contributionPct": 0.8}], "benchmark": {"changePct": 0.2}},
    }
    card, charts = invest_ai._daily_review_default(home, portfolio)
    assert [s["key"] for s in card["sections"]][:3] == ["market", "structure", "portfolio"]
    assert any(s["key"] == "moves" for s in card["sections"])
    assert len(charts) == 2
    assert "样本" not in card["summary"]


def test_stock_diagnosis_validator_requires_seven_sections():
    keys = ("company", "performance", "valuation", "capital", "institution", "highlights", "conclusion")
    sections = [
        {"key": key, "blocks": [{"type": "paragraph", "text": f"{key} 分析。"}]}
        for key in keys
    ]
    out = validate_stock_diagnosis(json.dumps({"summary": "结论", "sections": sections}), TaskRequest())
    assert [s["key"] for s in out["sections"]] == list(keys)


def test_stock_diagnosis_default_has_tables_and_charts():
    ctx = {
        "quote": {"code": "600519", "name": "贵州茅台", "industry": "白酒", "market": "CN", "price": 1500},
        "report": {"period": "2026Q3", "revenue": 100, "revenueYoY": 8, "netProfit": 50, "profitYoY": 10, "grossMargin": 90, "roe": 30, "ocf": 55},
        "valuation": {"pe": 20, "pb": 8, "pePercentile": 40},
        "fundFlow": {"five_day": 2, "twenty_day": 5, "series": [{"date": f"2026-11-0{i}", "value": i} for i in range(1, 6)]},
        "financialTrend": {"items": [{"label": f"2025Q{i}", "revenue": 90 + i, "net_profit": 40 + i, "net_margin": 20} for i in range(1, 6)]},
        "risks": [{"title": "估值偏高", "detail": "分位较高"}],
        "dataSource": "测试数据",
    }
    card, charts = invest_ai._stock_diagnosis_default(ctx)
    assert [s["key"] for s in card["sections"]] == ["company", "performance", "valuation", "capital", "institution", "highlights", "conclusion"]
    assert any(b.get("type") == "table" for s in card["sections"] for b in s["blocks"])
    assert len(charts) >= 2
    merged = invest_ai._merge_block_card(card, {"summary": "AI 结论", "sections": [{"key": "performance", "blocks": [{"type": "paragraph", "text": "AI 业绩分析"}]}]})
    assert merged["summary"] == "AI 结论"
    perf = next(s for s in merged["sections"] if s["key"] == "performance")
    assert perf["blocks"][0]["text"] == "AI 业绩分析"
    assert any(b.get("type") == "table" for b in perf["blocks"])


def test_stock_deep_rule_fallback_has_five_sections():
    card = invest_ai._stock_deep_rule_card({
        "dataSource": "测试数据",
        "dimensionFacts": {
            "fundamental": {"name": "贵州茅台", "reportPeriod": "2026Q3", "revenue": 100, "netProfit": 50},
            "profitability": {"grossMargin": 90, "roe": 30},
            "valuation": {"pe": 20, "pePercentile": 40},
            "risk": {"triggered": [{"title": "估值分位偏高", "detail": "测试"}]},
            "capital": {"latest": 1.2, "fiveDay": 2.3, "twentyDay": -1.1},
        },
    })
    assert [s["key"] for s in card["sections"]] == [
        "fundamental", "profitability", "valuation", "risk", "capital",
    ]
    assert card["meta"]["engine"] == "rule"
    assert "非投资建议" in card["disclaimer"]
    assert "贵州茅台" in card["summary"]


def test_factor_meta_exposes_stable_id_and_params():
    from services.invest import quant

    meta = quant._factor_meta("momentum")
    assert meta["id"] == "momentum"
    assert meta["params"] == {}
    assert meta["category"] == "momentum"


def test_stock_deep_endpoint_falls_back_when_llm_missing(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        invest_ai,
        "_stock_context",
        lambda conn, code, deep=False: {
            "dataSource": "测试数据",
            "dimensionFacts": {},
        },
    )

    def no_llm(*_args, **_kwargs):
        raise HTTPException(status_code=503, detail="AI 未配置")

    monkeypatch.setattr(invest_ai, "_call", no_llm)
    out = invest_ai.stock_ai("600519", user={"id": 7}, conn=None, refresh=False)
    assert out["ok"] is True
    assert out["engine"] == "rule"
    assert out["fallback"] is True
    assert len(out["card"]["sections"]) == 5
    assert "charts" not in out


def test_ai_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_cache, "ROOT", tmp_path)
    key = ai_cache.make_key("invest.stock", {"code": "600519"}, "prompt")
    assert ai_cache.get(7, "call", key) is None
    ai_cache.put(7, "call", key, {"card": {"summary": "短结论"}})
    assert ai_cache.get(7, "call", key)["card"]["summary"] == "短结论"
    assert ai_cache.get(8, "call", key) is None
    assert ai_cache.clear(7) == 1


def test_call_uses_cache_until_refresh(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_cache, "ROOT", tmp_path)
    monkeypatch.setattr(agent_prompts, "resolve_prompt", lambda user_id, task_id, fallback: fallback)
    calls = {"n": 0}

    def fake_run_task(task_id, **_kwargs):
        calls["n"] += 1
        return {"data": {"summary": "很" * 80, "sections": [{"body": "不应展示"}]}}

    monkeypatch.setattr("ai.router.available_task", lambda task_id: True)
    monkeypatch.setattr("ai.router.run_task", fake_run_task)
    first = invest_ai._call("invest.stock", {"code": "600519"}, user_id=7)
    second = invest_ai._call("invest.stock", {"code": "600519"}, user_id=7)
    assert calls["n"] == 1
    assert second.get("cached") is True
    assert len(first["card"]["summary"]) == 80
    assert first["card"]["sections"] == []
    invest_ai._call("invest.stock", {"code": "600519"}, user_id=7, refresh=True)
    assert calls["n"] == 2


def test_compare_pair_fallback_parser():
    assert _extract_compare_pair("对比宁德时代和茅台的估值与财务") == ("宁德时代", "茅台")
    assert _extract_compare_pair("比较贵州茅台 vs 五粮液") == ("贵州茅台", "五粮液")
    assert _extract_compare_pair("对比 [标的A] 和 [标的B] 的估值与财务") == ("标的A", "标的B")


def test_agent_registry_has_editable_h5_agents():
    ids = {a["task_id"] for a in agent_prompts.AGENTS}
    assert {"invest.stock", "invest.stock_deep", "invest.portfolio", "invest.quant", "invest.paper"} <= ids
    assert agent_prompts.AGENT_BY_ID["invest.stock"]["editable"] is True
    assert agent_prompts.AGENT_BY_ID["invest.stock_deep"]["editable"] is True
    assert agent_prompts.AGENT_BY_ID["invest.intent"]["editable"] is False
    assert len(agent_prompts.AGENT_BY_ID["invest.stock"]["default_prompt"]) > 50
    assert "五维" in agent_prompts.AGENT_BY_ID["invest.stock_deep"]["name"]
