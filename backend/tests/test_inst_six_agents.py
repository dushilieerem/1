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
from services.institution import research_service as rs  # noqa: E402


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


def test_agent_payload_includes_evidence_and_valuation_model() -> None:
    payload = rs._agent_payload(
        {
            "company": {"symbol": "600519.SH"},
            "as_of": "2026-10-30",
            "evidence": [{"id": 11, "title": "2025 年报", "quote": "营收", "source": "ifind"}],
            "valuation_model": {"base": 12.3, "available": True},
        },
        "valuation",
    )
    assert payload["evidence"][0]["id"] == 11
    assert payload["valuation_model"]["base"] == 12.3


def test_validate_dimension_filters_unknown_evidence_ids() -> None:
    from ai.router.specs import TaskRequest

    data = validate_dimension(
        json.dumps(
            {
                "summary": "财务质量稳定。",
                "checks": ["OCF/净利 1.1"],
                "evidence_ids": [11, 99],
                "confidence": 0.7,
            },
            ensure_ascii=False,
        ),
        TaskRequest(variables={"evidence_ids": [11]}),
    )
    assert data["evidence_ids"] == [11]


def test_validate_dimension_keeps_impact_and_data_used() -> None:
    data = validate_dimension(
        json.dumps(
            {
                "summary": "财务质量稳定。",
                "analysis_md": "第一段事实。\n\n第二段解释。\n\n第三段判断。",
                "impact": "支撑估值，但不构成买入指令。",
                "data_used": ["2025 年报营收", "现金流量表 OCF", ""],
                "checks": ["OCF/净利 1.1"],
                "confidence": 0.7,
            },
            ensure_ascii=False,
        ),
        None,  # type: ignore[arg-type]
    )
    assert data["impact"] == "支撑估值，但不构成买入指令。"
    assert data["data_used"] == ["2025 年报营收", "现金流量表 OCF"]
    assert data["analysis_md"].count("段") == 3


def test_humanize_text_replaces_internal_terms() -> None:
    from services.institution.common import humanize_text

    text = humanize_text("OCF/净利 0.22，DIO 170 天，PE_TTM 30.25x，E1505，17.1pct，+2.4pp。")
    assert "经营现金流/净利润" in text
    assert "存货周转天数" in text
    assert "市盈率（最近十二个月）" in text
    assert "证据 1505" in text
    assert "17.1 个百分点" in text
    assert "+2.4 个百分点" in text


def test_approval_memo_humanizes_internal_terms() -> None:
    from services.institution import ai_service

    out = ai_service._humanize_memo_output(
        {
            "summary": "六维均分2.33，净现比0.26，A级证据缺失，gate=fail。",
            "risks": ["治理 fail"],
            "open_questions": ["监控条无阈值"],
        }
    )
    assert "六个维度平均评分" in out["summary"]
    assert "经营现金流/净利润" in out["summary"]
    assert "最高等级证据" in out["summary"]
    assert "gate=fail" not in out["summary"]
    assert "治理关键项未通过核验" in out["risks"][0]


def test_chief_memo_humanizes_internal_enums() -> None:
    from services.institution import ai_service

    memo = ai_service._ensure_chief_memo_fields(
        {
            "chief_call": "现金含量 0.22 与治理 fail 并存，watch。",
            "summary": "proceed",
            "conclusion": "治理 fail",
            "decision": "watch",
            "risks": ["gate=fail"],
        },
        {"six_dim": [], "industry_analysis": {}},
        {},
    )
    assert "治理 fail" not in memo["chief_call"]
    assert "治理关键项未通过核验" in memo["chief_call"]
    assert "观察" in memo["chief_call"]
    assert memo["summary"] == "建议进入议案"
    assert "gate=fail" not in memo["risks"][0]


def test_professional_coverage_is_deterministic() -> None:
    from services.institution import ai_service

    rows = ai_service._professional_coverage(
        {
            "industry_analysis": {"gate": "watch", "score_10": 7.0, "confidence": 0.75},
            "six_dim": [
                {"key": "financial", "title": "财务质量", "gate": "pass", "score_10": 8.2, "confidence": 0.8},
                {"key": "moat", "title": "护城河", "gate": "watch", "score_10": 5.2, "confidence": 0.6},
            ],
        }
    )
    assert [r["key"] for r in rows] == ["industry_overview", "financial", "moat"]
    assert rows[0]["role_title"] == "行业分析 Agent"
    assert rows[0]["verdict"] == "保留"
    assert rows[1]["verdict"] == "支持"
    assert rows[2]["verdict"] == "待补"


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


def test_score_fields_keep_legacy_rating_and_note_benchmark() -> None:
    no_benchmark = svc._score_fields({"rating": 4, "score_10": 8.2})
    assert no_benchmark["rating"] == 4
    assert no_benchmark["score_10"] == 8.2
    assert "基准" in no_benchmark["rating_note"]

    with_benchmark = svc._score_fields({"rating": 4, "rating_benchmark": "同业中位 3.8/5"})
    assert with_benchmark["rating"] == 4
    assert with_benchmark["score_10"] == 8.0
    assert with_benchmark["rating_benchmark"] == "同业中位 3.8/5"

    rule_fallback = svc._score_fields({"gate": "watch", "confidence": 0.5})
    assert rule_fallback["score_10"] == 5.5
    assert "规则兜底" in rule_fallback["rating_note"]


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


def test_opportunity_source_keeps_clean_reason_from_idea_dict() -> None:
    out = rs._opportunity_source(
        {}, "push", {"source": "push", "why_now": "近 20 日动量 38.1%；PE TTM 24.81"}
    )
    assert out["source_detail"] == "近 20 日动量 38.1%；PE TTM 24.81"
    assert "{" not in out["source_detail"]


def test_merge_agent_results_skips_missing_dimension_without_score() -> None:
    built = {
        "dims": [
            {"key": "governance", "title": "CEO 与治理", "question": "治理是否可信？", "evidence_idx": []}
        ],
        "evidence": [],
        "data_gaps": [],
        "facts": {
            "as_of": "2026-10-30",
            "data_completeness": {
                "governance": {"level": "missing", "missing": ["实控人履历", "关联交易"]}
            },
        },
    }
    merged = svc._merge_agent_results(
        built, {"governance": {"skipped": True, "error": "数据未接入，暂不分析"}}, ["governance"]
    )
    dim = merged["dims"][0]
    assert dim["status"] == "skipped"
    assert dim["engine"] == "skipped"
    assert dim["summary"] == "数据未接入，暂不分析。"
    assert dim["score_10"] is None and dim["rating"] is None
    assert dim["gate"] == "fail"
    assert merged["agent_states"]["governance"] == "skipped"
    assert "实控人履历" in merged["data_gaps"]


def test_one_pager_metrics_are_deterministic() -> None:
    from services.institution import ai_service

    dims = []
    for i, key in enumerate(["industry", "business_model", "moat", "financial", "governance", "valuation"]):
        dims.append(
            {
                "key": key,
                "score_10": 5.5,
                "rating": 2.75,
                "confidence": 0.6,
                "gate": "fail" if key == "governance" else "watch",
            }
        )
    version = {
        "six_dim": dims,
        "valuation": {"low": 43.43, "base": 57.91, "high": 72.38, "method": "owner_earnings_proxy_net_debt"},
    }
    metrics = ai_service._one_pager_metrics(version, {"symbol": ""})
    by_label = {m["label"]: m for m in metrics}
    assert by_label["价值区间"]["value"] == "43.43–72.38 元"
    assert by_label["有效维"]["value"] == "5/6"
    assert "低置信维" not in by_label


def test_governance_guarantee_not_applicable_unlocks_core() -> None:
    docs = {
        "controller_profile": "have",
        "board_structure": "have",
        "pledge_freeze": "have",
        "related_party": "have",
        "litigation_penalty": "have",
    }
    completeness = svc._data_completeness(
        ind={}, peers=[], history={}, fin=[], val={}, documents=docs, na_fields={"guarantee": "银行/公司不适用"}
    )
    governance = completeness["governance"]
    assert governance["level"] == "sufficient"
    assert "gate_cap" not in governance
    assert "对外担保" not in governance["missing"]
    assert any("对外担保" in x and "不适用" in x for x in governance["have"])


def test_dimension_string_counter_is_not_split_into_chars() -> None:
    from ai.router.tasks.institution import validate_dimension

    raw = json.dumps({"summary": "结论", "counter": "单一反证条件，不应拆字"}, ensure_ascii=False)
    data = validate_dimension(raw, None)  # type: ignore[arg-type]
    assert data["counter"] == ["单一反证条件，不应拆字"]


def test_one_pager_bank_value_range_is_not_applicable() -> None:
    from services.institution import ai_service

    metrics = ai_service._one_pager_metrics(
        {"six_dim": [], "valuation": {"method": "relative_only"}}, {"symbol": ""}
    )
    by_label = {m["label"]: m for m in metrics}
    assert "不适用" in by_label["价值区间"]["value"]
    assert "PB/ROE" in by_label["价值区间"]["note"]


def test_rule_memo_uses_data_gaps_when_counter_is_char_array() -> None:
    from services.institution import ai_service

    version = {
        "six_dim": [{
            "key": "business_model",
            "title": "公司商业模式",
            "counter": ["缺", "客", "户"],
            "data_gaps": ["缺前五大客户占比，影响 H，需年报附注补。"],
        }],
        "valuation": {},
    }
    memo = ai_service._rule_memo(version)
    assert memo["risks"] == ["缺前五大客户占比，影响 H，需年报附注补。"]


def test_memo_gate_note_uses_chinese_titles_and_gate_wording() -> None:
    from services.institution import ai_service

    version = {
        "six_dim": [
            {"key": "industry", "title": "商业与产业", "gate": "fail"},
            {"key": "valuation", "title": "估值与价格", "gate": "fail"},
        ],
        "industry_analysis": {},
    }
    memo = ai_service._apply_memo_data_gate({"decision": "watch"}, version)
    assert "门禁未通过" in memo["data_gate_note"]
    assert "行业分析" in memo["data_gate_note"]
    assert "估值与价格" in memo["data_gate_note"]
