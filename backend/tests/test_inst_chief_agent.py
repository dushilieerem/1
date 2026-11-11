# -*- coding: utf-8 -*-
"""Chief Agent：只读工具与 tool-calling 循环。"""
from __future__ import annotations

import json

from services.institution import chief_agent


def _case() -> dict:
    return {
        "symbol": "600519.SH",
        "company_name": "贵州茅台",
        "evidence": [
            {"id": 11, "title": "2025 年报营收", "quote": "营收同比增长 18%", "source": "ifind", "grade": "B"},
            {"id": 12, "title": "现金流", "quote": "OCF/净利 1.1", "source": "ifind", "grade": "B"},
        ],
    }


def _version() -> dict:
    return {
        "version_no": 1,
        "cutoff": "2026-10-30",
        "valuation": {"base": 18.0, "low": 15.0, "high": 21.0},
        "industry_analysis": {"gate": "watch", "confidence": 0.7, "summary": "行业数据部分"},
        "six_dim": [
            {"key": "financial", "title": "财务质量", "gate": "pass", "confidence": 0.8, "summary": "现金流稳定"},
            {"key": "valuation", "title": "估值与价格", "gate": "watch", "confidence": 0.7, "summary": "分位偏高"},
        ],
    }


def test_research_tool_context_returns_evidence_and_specialists() -> None:
    ctx = chief_agent.ResearchToolContext(_case(), _version())
    specialists = ctx.list_specialists()
    assert specialists["ok"] is True
    assert any(x["key"] == "financial" for x in specialists["items"])
    found = ctx.search_evidence("营收")
    assert found["items"][0]["id"] == 11
    output = ctx.get_specialist_output("financial")
    assert output["summary"] == "现金流稳定"


def test_chief_agent_tool_loop_then_final_memo(monkeypatch) -> None:
    monkeypatch.setattr(chief_agent, "available_task", lambda _task: True)
    calls = {"n": 0}

    def fake_run_task(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": "",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "list_specialists", "arguments": "{}"},
                        }
                    ],
                },
            }
        return {
            "content": json.dumps(
                {
                    "decision": "proceed",
                    "summary": "财务与估值支持继续研究。",
                    "chief_call": "财务与估值支持继续研究，行业数据仍未验证。",
                    "chief_reasons": [
                        {
                            "agent_key": "financial",
                            "agent_name": "财务质量",
                            "reason": "现金流稳定",
                            "evidence_ids": [12],
                            "data": "OCF/净利 1.1",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            "message": {"role": "assistant", "content": "{}"},
        }

    monkeypatch.setattr(chief_agent, "run_task", fake_run_task)
    data = chief_agent.run_chief_agent(_case(), _version(), {"company": {"symbol": "600519.SH"}}, "system")
    assert data is not None
    assert data["chief_call"].startswith("财务与估值")
    assert len(data["agent_trace"]) == 1
    assert data["agent_trace"][0]["tool"] == "list_specialists"
    assert calls["n"] == 2
