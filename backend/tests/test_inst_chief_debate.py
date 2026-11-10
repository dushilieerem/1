# -*- coding: utf-8 -*-
"""辩论主持裁决：chair_review 校验与规则兜底。"""
from __future__ import annotations

import json

from ai.router.specs import TaskRequest
from ai.router.tasks.institution import validate_debate
from services.institution.debate_service import _debate_fallback


def test_validate_debate_preserves_and_normalizes_chair_review() -> None:
    out = validate_debate(
        json.dumps(
            {
                "bull": [{"claim": "财务与估值支持跟踪", "evidence_ids": [1]}],
                "bear": [{"claim": "证据链未闭环", "evidence_ids": [2]}],
                "chair": [{"claim": "先补证据", "evidence_ids": [1]}],
                "chair_review": {
                    "verdict": "补充研究",
                    "chair_call": "证据链未闭环，先补数据。",
                    "consensus": ["财务数据可用"],
                    "unresolved": [
                        {
                            "issue": "行业份额",
                            "bull_view": "份额提升",
                            "bear_view": "缺第三方数据",
                            "why_unresolved": "未接入行业数据",
                            "data_needed": "行业 TAM/CR5",
                        }
                    ],
                    "accepted_claims": [{"side": "多", "claim_id": "B1", "reason": "财务证据充分"}],
                    "rejected_claims": [{"side": "空", "claim_id": "S1", "reason": "缺证据"}],
                    "what_would_change": ["行业数据补齐（下一轮）"],
                    "chief_confidence": 0.7,
                },
            }
        ),
        TaskRequest(variables={"evidence_ids": [1, 2]}),
    )
    review = out["chair_review"]
    assert review["schema_version"] == "chief-debate-v1"
    assert review["agent_tier"] == "chief"
    assert review["role_title"] == "主持（合伙人）"
    assert review["verdict"] == "supplement_research"
    assert review["chair_call"].startswith("证据链")
    assert review["unresolved"][0]["data_needed"] == "行业 TAM/CR5"
    assert review["accepted_claims"][0]["side"] == "bull"
    assert review["rejected_claims"][0]["side"] == "bear"
    assert review["chief_confidence"] == 0.7


def test_validate_debate_falls_back_without_chair_review() -> None:
    out = validate_debate(
        json.dumps(
            {
                "bull": [{"claim": "看多", "evidence_ids": [1]}],
                "bear": [{"claim": "看空", "evidence_ids": [2]}],
                "chair": [{"claim": "证据不足，补充研究", "evidence_ids": [1]}],
            }
        ),
        TaskRequest(variables={"evidence_ids": [1, 2]}),
    )
    review = out["chair_review"]
    assert review["verdict"] == "supplement_research"
    assert review["chief_fields_fallback"] is True
    assert review["chief_confidence"] == 0.5


def test_debate_rule_fallback_has_chair_review() -> None:
    out = _debate_fallback(
        {"symbol": "600519.SH", "name": "贵州茅台"},
        [{"id": 1, "title": "年报", "quote": "q", "source": "filing"}],
        None,
    )
    assert out["chair_review"]["verdict"] == "supplement_research"
    assert out["chair_review"]["unresolved"]
    assert out["chair_review"]["chief_fields_fallback"] is True
