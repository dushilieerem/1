# -*- coding: utf-8 -*-
"""机构端六维 Agent：TaskSpec 校验与结果合并。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.router.tasks.institution import DIMENSION_TASKS, validate_dimension  # noqa: E402
from services.institution import inst_service as svc  # noqa: E402


def test_six_dimension_tasks_registered() -> None:
    assert set(DIMENSION_TASKS) == {
        "industry",
        "business_model",
        "moat",
        "financial",
        "governance",
        "valuation",
    }
    assert DIMENSION_TASKS["industry"].task_id == "inst.dim.industry"


def test_validate_dimension_normalizes_evidence_and_confidence() -> None:
    raw = json.dumps(
        {
            "summary": "行业集中度较高，龙头有定价权。",
            "checks": ["CR5 未知", ""],
            "counter": ["数据缺口"],
            "evidence": [{"title": "行业", "quote": "待补充", "source": "ifind"}, {"title": ""}],
            "open_questions": ["份额数据"],
            "confidence": 2.5,
            "data_gaps": ["行业规模"],
        },
        ensure_ascii=False,
    )
    data = validate_dimension(raw, None)  # type: ignore[arg-type]
    assert data["checks"] == ["CR5 未知"]
    assert data["evidence"] == [{"title": "行业", "quote": "待补充", "source": "ifind"}]
    assert data["confidence"] == 1.0


def test_merge_agent_results_keeps_six_dims_and_fallback() -> None:
    built = {
        "dims": [
            {"key": key, "title": title, "question": q, "evidence_idx": []}
            for key, title, q in svc.SIX_DIM_DEFS
        ],
        "evidence": [],
        "data_gaps": [],
        "facts": {"as_of": "2026-10-30"},
    }
    results = {}
    for key, _, _ in svc.SIX_DIM_DEFS:
        results[key] = {
            "data": {
                "summary": f"{key} summary",
                "checks": ["check"],
                "counter": ["counter"],
                "evidence": [{"title": f"{key} evidence", "quote": "quote", "source": "ifind"}],
                "open_questions": [],
                "confidence": 0.6,
                "data_gaps": [],
            }
        }
    results["governance"] = {"error": "AI 未配置"}
    merged = svc._merge_agent_results(built, results, [k for k, _, _ in svc.SIX_DIM_DEFS])
    assert len(merged["dims"]) == 6
    assert merged["agent_states"]["industry"] == "done"
    assert merged["agent_states"]["governance"] == "failed"
    gov = next(d for d in merged["dims"] if d["key"] == "governance")
    assert gov["engine"] == "rule"
    assert gov["agent_error"] == "AI 未配置"
    assert len(merged["evidence"]) == 5


def test_agent_payload_marks_governance_gap() -> None:
    facts = {
        "company": {"symbol": "000001.SZ"},
        "as_of": "2026-10-30",
        "price": 10,
        "valuation": {"pe_ttm": 5},
        "percentile": {},
        "risk": {},
        "industry": {},
        "financials": [],
        "data_gaps": [],
    }
    payload = svc._agent_payload(facts, "governance")
    assert "governance_note" in payload
    assert payload["market_data"]["price"] == 10


def test_merge_industry_block_is_separate_from_six_dims() -> None:
    built = {"evidence": [], "facts": {"as_of": "2026-10-30"}}
    block = svc._merge_industry(
        built,
        {
            "data": {
                "summary": "行业增速 8%，竞争格局稳定。",
                "checks": ["空间 1000 亿"],
                "counter": ["增速低于预期"],
                "open_questions": ["份额"],
                "data_gaps": [],
                "evidence": [{"title": "行业规模", "quote": "1000 亿", "source": "ifind"}],
                "confidence": 0.6,
            }
        },
        {},
    )
    assert block["key"] == "industry"
    assert block["summary"].startswith("行业增速")
    assert block["evidence_idx"] == [0]
    assert built["evidence"][0]["title"] == "行业规模"


def test_validate_dimension_accepts_a04_six_dim_contract() -> None:
    raw = json.dumps(
        {
            "dimension": "industry_position",
            "rating": 4,
            "gate": "pass",
            "one_line": "份额有望从 25% 升至 35%（E17）",
            "analysis_md": "① 结论：卡位成立。\n\n② 份额与驱动：……",
            "key_numbers": [
                {"name": "份额", "value": "25%", "period": "2025A", "source": "E17", "evidence_id": "E17", "caliber": "收入口径"}
            ],
            "evidence": [
                {"evidence_id": "E17", "grade": "A", "document_id": "年报", "page": "12", "quote": "份额 25%"}
            ],
            "falsifiers": [
                {"condition": "份额跌破 20%", "threshold": "20%", "observe": "季度份额", "frequency": "季度"}
            ],
            "data_gaps": [{"item": "渠道库存", "impact": "M", "workaround": "经销商调研"}],
            "confidence": "H",
        },
        ensure_ascii=False,
    )
    data = validate_dimension(raw, None)  # type: ignore[arg-type]
    assert data["summary"].startswith("份额有望从 25% 升至 35%")
    assert data["checks"][0].startswith("份额：25%")
    assert data["counter"][0].startswith("份额跌破 20%")
    assert data["open_questions"][0].startswith("渠道库存")
    assert data["confidence"] == 0.9
    assert data["confidence_label"] == "H"
    assert data["rating"] == 4
    assert data["gate"] == "pass"
    assert data["analysis_md"].startswith("① 结论")


def test_validate_memo_accepts_a19_and_a20_contracts() -> None:
    from ai.router.tasks.institution import validate_memo

    risk = validate_memo(
        json.dumps(
            {
                "verdict": "block",
                "reason": "集中度 18% 超过 15% 硬上限。",
                "checks": [
                    {"item": "concentration", "status": "block", "detail": "交易后 18% > 15%", "evidence_ids": ["E1"]},
                    {"item": "cash", "status": "pass", "detail": "交易后 12%"},
                ],
                "conditions": [{"text": "降至 15% 以下再提交"}],
            },
            ensure_ascii=False,
        ),
        None,  # type: ignore[arg-type]
    )
    assert risk["summary"].startswith("集中度 18%")
    assert risk["risks"][0].startswith("concentration")
    assert risk["open_questions"] == ["降至 15% 以下再提交"]
    assert risk["evidence"] == ["E1"]

    chairman = validate_memo(
        json.dumps(
            {
                "decision": "conditional",
                "reason": "资本配置可接受，带条件批准。",
                "checks": [
                    {"item": "partner", "pass": True, "note": "已通过"},
                    {"item": "risk", "pass": False, "note": "风控附加条件未满足"},
                ],
                "conditions": [{"text": "执行前确认条件"}],
                "unresolved": [{"issue": "渠道库存待核"}],
                "memo_md": "审批备忘录全文。",
            },
            ensure_ascii=False,
        ),
        None,  # type: ignore[arg-type]
    )
    assert chairman["summary"].startswith("资本配置可接受")
    assert any("risk" in x for x in chairman["risks"])
    assert "执行前确认条件" in chairman["open_questions"]
    assert "渠道库存待核" in chairman["open_questions"]
