# -*- coding: utf-8 -*-
"""H5 AI 的 50 字限制、落盘缓存与 Agent 注册表。"""
from __future__ import annotations

from app.routers import invest_ai
from app.routers.invest_ai import _clip50, _compact_result, _extract_compare_pair
from services.invest import agent_prompts, ai_cache


def test_clip50_and_compact_card():
    assert len(_clip50("很" * 80)) <= 50
    out = _compact_result({
        "card": {
            "summary": "很" * 80,
            "sections": [{"title": "长文", "body": "很" * 200}],
            "disclaimer": "AI 生成 · 非投资建议",
        }
    })
    assert len(out["card"]["summary"]) <= 50
    assert out["card"]["sections"] == []
    assert out["card"]["disclaimer"]


def test_compact_card_falls_back_to_section_body():
    out = _compact_result({"card": {"summary": "", "sections": [{"body": "估值偏高，先看盈利。"}]}})
    assert out["card"]["summary"] == "估值偏高，先看盈利。"


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
    assert len(first["card"]["summary"]) <= 50
    assert first["card"]["sections"] == []
    invest_ai._call("invest.stock", {"code": "600519"}, user_id=7, refresh=True)
    assert calls["n"] == 2


def test_compare_pair_fallback_parser():
    assert _extract_compare_pair("对比宁德时代和茅台的估值与财务") == ("宁德时代", "茅台")
    assert _extract_compare_pair("比较贵州茅台 vs 五粮液") == ("贵州茅台", "五粮液")
    assert _extract_compare_pair("对比 [标的A] 和 [标的B] 的估值与财务") == ("标的A", "标的B")


def test_agent_registry_has_editable_h5_agents():
    ids = {a["task_id"] for a in agent_prompts.AGENTS}
    assert {"invest.stock", "invest.portfolio", "invest.quant", "invest.paper"} <= ids
    assert agent_prompts.AGENT_BY_ID["invest.stock"]["editable"] is True
    assert agent_prompts.AGENT_BY_ID["invest.intent"]["editable"] is False
    assert len(agent_prompts.AGENT_BY_ID["invest.stock"]["default_prompt"]) > 50
