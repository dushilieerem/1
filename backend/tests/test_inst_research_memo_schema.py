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


def test_research_memo_maps_buy_and_defaults_invalid_to_watch() -> None:
    buy = validate_research_memo(
        json.dumps({"summary": "买入", "decision": "buy", "six_dim_scores": "bad"}),
        TaskRequest(),
    )
    assert buy["decision"] == "proceed"
    assert buy["six_dim_scores"] == []
    assert buy["conflicts"] == []
    assert buy["key_variables"] == []

    invalid = validate_research_memo(
        json.dumps({"summary": "观察", "decision": "maybe"}),
        TaskRequest(),
    )
    assert invalid["decision"] == "watch"


def test_research_memo_normalizes_chief_fields() -> None:
    out = validate_research_memo(
        json.dumps(
            {
                "decision": "proceed",
                "chief_call": "贵州茅台财务与估值支持继续研究。",
                "chief_reasons": [
                    {
                        "agent_key": "financial",
                        "agent_name": "财务质量",
                        "reason": "OCF/净利稳定。",
                        "evidence_ids": [12, "bad"],
                        "data": "OCF/净利 1.1",
                    }
                ],
                "strongest_counterpoint": {
                    "point": "行业份额未验证",
                    "response": "只影响置信度",
                    "evidence_ids": [21],
                    "overturns": False,
                },
                "key_assumptions": ["需求不塌"],
                "what_would_change": ["OCF/净利 <0.7（季频）"],
                "chief_confidence": 1.5,
                "summary": "结论先行",
            }
        ),
        TaskRequest(),
    )
    assert out["schema_version"] == "chief-research-v1"
    assert out["agent_tier"] == "chief"
    assert out["role_title"] == "研究经理"
    assert out["chief_call"].startswith("贵州茅台")
    assert out["chief_reasons"][0]["evidence_ids"] == [12]
    assert out["strongest_counterpoint"]["point"] == "行业份额未验证"
    assert out["chief_confidence"] == 1.0
    assert out["chief_fields_fallback"] is False


def test_research_memo_marks_missing_chief_fields_for_fallback() -> None:
    out = validate_research_memo(
        json.dumps({"decision": "watch", "summary": "先观察"}),
        TaskRequest(),
    )
    assert out["schema_version"] == "chief-research-v1"
    assert out["chief_call"] == "先观察"
    assert out["chief_fields_fallback"] is True
    assert out["chief_confidence"] == 0.5


def test_research_memo_accepts_a10_dimension_scores_and_price_band() -> None:
    out = validate_research_memo(
        json.dumps(
            {
                "decision": "buy",
                "price_band": [12, 16],
                "base_value": 18,
                "mos": 0.3,
                "holding_period": "1-3 年，按季复核",
                "dimension_scores": [
                    {
                        "dimension": "industry_position",
                        "rating": 4,
                        "gate": "pass",
                        "confidence": "H",
                        "one_line": "份额提升 2pct（E17）",
                    }
                ],
                "conflicts": [
                    {"issue": "行业与财务分歧", "ruling": "以审计数据为准", "unresolved": False}
                ],
                "key_variable": {
                    "name": "份额",
                    "current": "25%",
                    "threshold": "20%",
                    "source": "E17",
                    "frequency": "季度",
                },
                "pre_mortem": [{"reason": "价格战", "probability": 0.4, "early_signal": "吨价跌破成本"}],
                "unresolved": [{"issue": "渠道库存"}],
                "memo_md": "结论：买入。\n\n三条理由……",
            }
        ),
        TaskRequest(),
    )
    assert out["decision"] == "proceed"
    assert out["summary"].startswith("结论：买入")
    assert out["six_dim_scores"][0]["key"] == "industry"
    assert out["six_dim_scores"][0]["score"] == 4.0
    assert out["six_dim_scores"][0]["confidence"] == 0.9
    assert out["price_range"]["low"] == 12.0
    assert out["price_range"]["high"] == 16.0
    assert out["conflicts"][0].startswith("行业与财务分歧")
    assert out["key_variables"][0].startswith("份额：当前 25%")
    assert out["risks"][0].startswith("价格战")
    assert out["open_questions"] == ["渠道库存"]
    assert out["holding_period"] == "1-3 年，按季复核"
