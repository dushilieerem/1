# -*- coding: utf-8 -*-
"""H5 AI 卡片归一化、落盘缓存与 Agent 注册表。"""
from __future__ import annotations

import json

import pytest
from ai.errors import AiBadOutput
from ai.router.specs import TaskRequest
from ai.router.tasks.invest import validate_stock_deep
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


def test_stock_deep_validator_normalizes_five_dimensions():
    sections = [
        {"key": key, "title": "模型乱写的标题", "body": f"{key} 的事实。", "items": [{"k": "指标", "v": "1"}]}
        for key in ("capital", "risk", "valuation", "profitability", "fundamental")
    ]
    out = validate_stock_deep(json.dumps({"summary": "总体平稳。", "sections": sections}), TaskRequest())
    assert [s["title"] for s in out["sections"]] == ["基本面", "盈利", "估值", "风险", "资金"]


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
