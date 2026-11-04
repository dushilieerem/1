# -*- coding: utf-8 -*-
"""CIO 一页纸输出契约：研究建议、六维评分与分歧字段。"""
from __future__ import annotations

import json

from ai.router.specs import TaskRequest
from ai.router.tasks.institution import validate_research_memo


def test_research_memo_keeps_supported_decision_and_scores() -> None:
    out = validate_research_memo(
        json.dumps(
            {
                "summary": "结论先行",
                "decision": "avoid",
                "six_dim_scores": [
                    {"key": "industry", "score": 2, "confidence": 0.7, "note": "份额下滑"},
                    {"key": "unknown", "score": 5, "confidence": 1, "note": "应被过滤"},
                    {"key": "financial", "score": 9, "confidence": 1, "note": "超范围"},
                ],
                "conflicts": ["行业判断与财务证据不一致"],
                "key_variables": ["份额", "FCF"],
                "risks": ["份额继续下滑"],
                "open_questions": ["下一季份额"],
            }
        ),
        TaskRequest(),
    )
    assert out["decision"] == "avoid"
    assert [item["key"] for item in out["six_dim_scores"]] == ["industry"]
    assert out["six_dim_scores"][0]["score"] == 2.0
    assert out["conflicts"] == ["行业判断与财务证据不一致"]
    assert out["key_variables"] == ["份额", "FCF"]


def test_research_memo_defaults_to_watch_for_invalid_decision() -> None:
    out = validate_research_memo(
        json.dumps({"summary": "观察", "decision": "buy", "six_dim_scores": "bad"}),
        TaskRequest(),
    )
    assert out["decision"] == "watch"
    assert out["six_dim_scores"] == []
    assert out["conflicts"] == []
    assert out["key_variables"] == []
