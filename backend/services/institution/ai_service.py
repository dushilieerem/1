# -*- coding: utf-8 -*-
"""机构端 AI 建议：研究备忘、维度对话、合伙人/风控/Chairman 建议与 Agent 提示词管理。

从 inst_service 拆出，函数名与签名不变；调用方仍从 inst_service 导入。"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Callable

from psycopg.types.json import Jsonb

from ai.runtime import agent_store
from ai.runtime.agent_store import (
    get_cached_output,
    get_effective_prompt,
    get_latest_output,
    input_hash as agent_input_hash,
    save_output,
)
from services.core.db import get_conn
from services.core.tenant import OrgScope
from services.institution.prompts import (
    CHAIRMAN_MEMO_PROMPT,
    PARTNER_MEMO_PROMPT,
    CHAT_PROMPT,
    INDUSTRY_PROMPT,
    DEBATE_PROMPT,
    DIMENSION_PROMPTS as _DIMENSION_PROMPTS,
    RESEARCH_MEMO_PROMPT,
    RISK_REVIEW_PROMPT,
    ROLE_PROMPTS as _ROLE_PROMPTS,
)
from services.institution import data_platform, inst_ai_store
from services.institution.report import render_research_report, report_filename
from services.marketdata import store as md

from . import repo
from .common import _clip_brief, _evidence_grade, _hash, _iso, _j, _pc, _row_dict, _yi
from .guards import POLICY_VERSION, _audit, _member, _require_role, _uid
from .stages import _record_gate, _record_transition, _set_case_stage, _stage_def, _stage_payload
from .company_service import MAX_SINGLE_WEIGHT, MIN_CASH_RATIO, _mapped_industry
from .debate_service import start_debate
from .guards import AiUnavailable
from .portfolio_service import portfolio
from .proposal_service import (
    _approval_rows,
    _approval_state,
    _current_version,
    _member_role_counts,
    _proposal_row,
    _research_debate_summary,
    _risk_checks,
    get_proposal,
)
from .research_service import (
    CHIEF_RESEARCH_ROLE_TITLE,
    CHIEF_RESEARCH_SCHEMA,
    PROFESSIONAL_ROLE_TITLES,
    SIX_DIM_DEFS,
    _clean_agent_text,
    _overall_score,
    get_case,
)
from .research_service import *   # noqa: F401,F403
from .debate_service import *    # noqa: F401,F403
from .exit_service import *      # noqa: F401,F403


def _ai_task(task_id: str, payload: dict[str, Any], system: str) -> dict[str, Any]:
    try:
        from ai.router import available_task, run_task
    except Exception as exc:  # pragma: no cover - 依赖缺失
        raise AiUnavailable(f"AI 路由层不可用：{exc}") from exc
    if not available_task(task_id):
        raise AiUnavailable("AI 未配置（缺少 LLM 网关或 Key）")
    system, _ = get_effective_prompt(task_id, system)
    out = run_task(
        task_id,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    data = out.get("data")
    if isinstance(data, dict):
        return data
    return {"summary": str(out.get("content") or "")}


def _memo_metrics(case: dict[str, Any]) -> list[dict[str, Any]]:
    """一页纸顶部指标：只展示已有数据，缺失不编造。"""
    symbol = str(case.get("symbol") or "")
    fin = md.financials(symbol, limit=2) or []
    latest = fin[0] if fin else {}
    val = md.valuation_latest(symbol) or {}
    pct = md.valuation_percentile(symbol, years=3) or {}
    out: list[dict[str, Any]] = []
    if latest.get("revenue") is not None:
        out.append(
            {
                "label": "营业收入",
                "value": _yi(latest.get("revenue")),
                "note": f"同比 {_pc(latest.get('revenue_yoy'))}"
                if latest.get("revenue_yoy") is not None
                else "最近报告期",
            }
        )
    if latest.get("net_profit") is not None:
        out.append(
            {
                "label": "净利润",
                "value": _yi(latest.get("net_profit")),
                "note": f"同比 {_pc(latest.get('profit_yoy'))}"
                if latest.get("profit_yoy") is not None
                else "最近报告期",
            }
        )
    if latest.get("roe") is not None:
        out.append({"label": "ROE", "value": _pc(latest.get("roe")), "note": "最近报告期"})
    if val.get("pe_ttm") is not None:
        out.append(
            {
                "label": "PE TTM",
                "value": f"{float(val['pe_ttm']):.2f}",
                "note": f"历史分位 {_pc(pct.get('pe_percentile'))}",
            }
        )
    elif val.get("pb_mrq") is not None:
        out.append(
            {
                "label": "PB MRQ",
                "value": f"{float(val['pb_mrq']):.2f}",
                "note": f"历史分位 {_pc(pct.get('pb_percentile'))}",
            }
        )
    return out


def _one_pager_metrics(version: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    """一页纸四张卡：价值区间、有效维、低置信维、PE，全部用确定性数据覆盖 AI 文案。"""
    dims = [d for d in (version.get("six_dim") or []) if isinstance(d, dict)]
    valid = [
        d
        for d in dims
        if (d.get("score_10") is not None or d.get("rating") is not None)
        and str(d.get("gate") or "") != "fail"
    ]
    low = []
    for d in dims:
        confidence = d.get("confidence")
        rating = d.get("rating")
        if (
            confidence is not None
            and float(confidence) < 0.66
        ) or (
            rating is not None
            and float(rating) < 3.3
        ):
            low.append(d)
    valuation = version.get("valuation") or {}
    if any(valuation.get(k) is not None for k in ("low", "base", "high")):
        low_v = valuation.get("low")
        high_v = valuation.get("high")
        base_v = valuation.get("base")
        if low_v is not None and high_v is not None:
            price_text = f"{float(low_v):.2f}–{float(high_v):.2f} 元"
        else:
            price_text = f"{float(base_v or low_v or high_v):.2f} 元"
        price_note = "研究区间，不是目标价"
    elif valuation.get("method") == "relative_only":
        price_text = "不适用（银行相对估值）"
        price_note = "金融企业不使用 DCF 目标价区间，仅看 PB/ROE 等相对估值"
    else:
        reason = str(valuation.get("reason") or valuation.get("error") or "未产出估值数据")
        price_text = "不适用（自由现金流为负）" if "自由现金流为负" in reason else "不可用"
        price_note = reason
    metrics: list[dict[str, Any]] = [
        {"label": "价值区间", "value": price_text, "note": price_note},
        {
            "label": "有效维",
            "value": f"{len(valid)}/{len(dims) or 6}",
            "note": "有评分且 gate≠fail",
        },
        {"label": "低置信维", "value": f"{len(low)} 项", "note": "confidence<0.66 或 rating<3.3"},
    ]
    symbol = str(case.get("symbol") or "")
    val = md.valuation_latest(symbol) or {}
    pct = md.valuation_percentile(symbol, years=3) or {}
    if val.get("pe_ttm") is not None:
        metrics.append(
            {
                "label": "PE_TTM",
                "value": f"{float(val['pe_ttm']):.2f}x",
                "note": f"历史分位 {_pc(pct.get('pe_percentile'))}",
            }
        )
    return metrics


def _merge_memo_metrics(
    memo: dict[str, Any], version: dict[str, Any], case: dict[str, Any]
) -> dict[str, Any]:
    try:
        required = _one_pager_metrics(version, case)
    except Exception:
        return memo
    existing = [m for m in (memo.get("metrics") or []) if isinstance(m, dict)]
    by_label = {str(m.get("label") or ""): m for m in existing if m.get("label")}
    for item in required:
        by_label[item["label"]] = item
    order = ["价值区间", "有效维", "低置信维", "PE_TTM"]
    merged = [by_label.pop(label) for label in order if label in by_label]
    merged.extend(by_label.values())
    memo["metrics"] = merged
    return memo


def _text_items(value: Any) -> list[str]:
    """兼容旧版本把 counter 存成字符串或字符数组的情况。"""
    if isinstance(value, str):
        return [value] if value.strip() else []
    items = [str(x) for x in (value or []) if str(x).strip()]
    if items and all(len(x) <= 1 for x in items):
        return ["".join(items)]
    return items


def _normalize_text_list(value: Any) -> list[str]:
    """把旧版本存的“长句 + 单字”合并回可读文本，避免一页纸逐字列风险。"""
    items = [str(x).strip() for x in (value or []) if str(x).strip()]
    out: list[str] = []
    buf: list[str] = []
    for item in items:
        if len(item) <= 1:
            buf.append(item)
            continue
        if buf:
            out.append("".join(buf))
            buf = []
        out.append(item)
    if buf:
        out.append("".join(buf))
    return out


def _dim_counter(dim: dict[str, Any]) -> list[str]:
    raw = dim.get("counter")
    # 旧版本可能把字符串 counter 存成字符数组；此时改用完整的 data_gaps。
    if isinstance(raw, list) and raw and all(len(str(x)) <= 1 for x in raw):
        return _text_items(dim.get("data_gaps") or dim.get("open_questions"))
    return _text_items(raw)


def _clamp_confidence(value: Any, default: float = 0.5) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 2)
    except (TypeError, ValueError):
        return default


def _score10(item: dict[str, Any]) -> float | None:
    if not isinstance(item, dict):
        return None
    if item.get("score_10") is not None:
        try:
            return round(max(0.0, min(10.0, float(item["score_10"]))), 1)
        except (TypeError, ValueError):
            return None
    if item.get("rating") is not None:
        try:
            return round(max(0.0, min(10.0, float(item["rating"]) * 2)), 1)
        except (TypeError, ValueError):
            return None
    return None


def _coverage_verdict(gate: Any, confidence: Any, score: float | None) -> str:
    gate_text = str(gate or "")
    if gate_text == "fail":
        return "阻断"
    try:
        conf = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        conf = None
    if conf is not None and conf < 0.66:
        return "待补"
    if score is None:
        return "待补"
    if score < 6.6:
        return "待补"
    if gate_text == "watch":
        return "保留"
    return "支持"


def _professional_coverage(version: dict[str, Any]) -> list[dict[str, Any]]:
    """一页纸看到的专业 Agent 覆盖表；由版本数据确定性生成，不采用模型自报。"""
    rows: list[dict[str, Any]] = []
    industry = version.get("industry_analysis") or {}
    if isinstance(industry, dict) and industry:
        score = _score10(industry)
        rows.append(
            {
                "key": "industry_overview",
                "name": "行业底图",
                "tier": "professional",
                "role_title": PROFESSIONAL_ROLE_TITLES["industry_overview"],
                "score_10": score,
                "rating_benchmark": industry.get("rating_benchmark"),
                "gate": industry.get("gate"),
                "confidence": _clamp_confidence(industry.get("confidence")),
                "verdict": _coverage_verdict(industry.get("gate"), industry.get("confidence"), score),
            }
        )
    for dim in version.get("six_dim") or []:
        if not isinstance(dim, dict) or not dim.get("key"):
            continue
        key = str(dim["key"])
        score = _score10(dim)
        rows.append(
            {
                "key": key,
                "name": str(dim.get("title") or key),
                "tier": "professional",
                "role_title": PROFESSIONAL_ROLE_TITLES.get(key, "专业研究 Agent"),
                "score_10": score,
                "rating_benchmark": dim.get("rating_benchmark"),
                "gate": dim.get("gate"),
                "confidence": _clamp_confidence(dim.get("confidence")),
                "verdict": _coverage_verdict(dim.get("gate"), dim.get("confidence"), score),
            }
        )
    return rows


def _is_chief_output(output: dict[str, Any] | None) -> bool:
    return isinstance(output, dict) and str(output.get("schema_version") or "") == CHIEF_RESEARCH_SCHEMA


def _fallback_chief_reasons(version: dict[str, Any]) -> list[dict[str, Any]]:
    dims = [d for d in (version.get("six_dim") or []) if isinstance(d, dict) and d.get("summary")]
    dims.sort(key=lambda d: (_score10(d) if _score10(d) is not None else -1), reverse=True)
    out: list[dict[str, Any]] = []
    for dim in dims[:3]:
        key = str(dim.get("key") or "")
        ids = dim.get("direct_evidence_ids") or dim.get("evidence_ids") or []
        out.append(
            {
                "agent_key": key,
                "agent_name": str(dim.get("title") or key),
                "reason": _clip_brief(dim.get("summary")),
                "evidence_ids": [int(x) for x in ids if str(x).isdigit()],
                "data": f"评分 {_score10(dim) if _score10(dim) is not None else '未评分'} / gate {dim.get('gate') or '未定'}",
            }
        )
    return out


def _ensure_chief_memo_fields(
    memo: dict[str, Any], version: dict[str, Any], case: dict[str, Any] | None = None
) -> dict[str, Any]:
    """给一页纸 memo 补齐可读字段，并过滤不存在于本版本证据包的 evidence id。"""
    data = dict(memo or {})
    raw_call = str(data.get("chief_call") or "").strip()
    chief_call = _clip_brief(raw_call or data.get("conclusion") or data.get("summary"))
    data["schema_version"] = CHIEF_RESEARCH_SCHEMA
    data["agent_tier"] = "chief"
    data["role_title"] = CHIEF_RESEARCH_ROLE_TITLE
    data["chief_call"] = chief_call

    raw_reasons = data.get("chief_reasons")
    reasons: list[dict[str, Any]] = []
    if isinstance(raw_reasons, list):
        for item in raw_reasons:
            if isinstance(item, dict) and str(item.get("reason") or "").strip():
                reasons.append(
                    {
                        "agent_key": str(item.get("agent_key") or ""),
                        "agent_name": _clip_brief(item.get("agent_name")),
                        "reason": _clip_brief(item.get("reason")),
                        "evidence_ids": [int(x) for x in (item.get("evidence_ids") or []) if str(x).isdigit()],
                        "data": _clip_brief(item.get("data")),
                    }
                )
    fallback_reasons = not reasons
    if fallback_reasons:
        reasons = _fallback_chief_reasons(version)
    data["chief_reasons"] = reasons[:3]

    counterpoint = data.get("strongest_counterpoint")
    if isinstance(counterpoint, str):
        counterpoint = {"point": _clip_brief(counterpoint), "response": "", "evidence_ids": [], "overturns": False}
    if not isinstance(counterpoint, dict) or not str(counterpoint.get("point") or "").strip():
        risks = _text_items(data.get("risks"))
        if not risks:
            for dim in version.get("six_dim") or []:
                if isinstance(dim, dict):
                    risks.extend(_text_items(dim.get("counter")))
        counterpoint = {
            "point": _clip_brief(risks[0]) if risks else "",
            "response": "服务端兜底，未做一页纸反证裁决",
            "evidence_ids": [],
            "overturns": False,
        }
    data["strongest_counterpoint"] = counterpoint

    assumptions = _text_items(data.get("key_assumptions"))
    if not assumptions:
        assumptions = _text_items(data.get("key_variables"))[:3]
    data["key_assumptions"] = assumptions[:4]

    changes = _text_items(data.get("what_would_change"))
    if not changes:
        changes = _text_items(data.get("open_questions"))[:3]
    data["what_would_change"] = changes[:4]

    data["chief_confidence"] = _clamp_confidence(data.get("chief_confidence") or data.get("confidence"))
    data["professional_coverage"] = _professional_coverage(version)
    data["chief_fields_fallback"] = bool(data.get("chief_fields_fallback") or not raw_call or fallback_reasons)

    valid_ids = {
        int(e["id"])
        for e in ((case or {}).get("evidence") or [])
        if isinstance(e, dict) and str(e.get("id") or "").isdigit()
    }
    if valid_ids:
        for reason in data["chief_reasons"]:
            reason["evidence_ids"] = [x for x in reason["evidence_ids"] if x in valid_ids]
        counterpoint["evidence_ids"] = [
            int(x) for x in (counterpoint.get("evidence_ids") or []) if str(x).isdigit() and int(x) in valid_ids
        ]
    return data


def _rule_memo(version: dict[str, Any], case: dict[str, Any] | None = None) -> dict[str, Any]:
    dims = [d for d in (version.get("six_dim") or []) if isinstance(d, dict)]
    risks = [c for d in dims for c in _dim_counter(d)][:5]
    questions = [
        q
        for d in dims
        for q in _text_items(d.get("open_questions") or d.get("data_gaps"))
    ][:8]
    valuation = version.get("valuation") or {}
    price_range = None
    if any(valuation.get(k) is not None for k in ("low", "base", "high")):
        price_range = {
            "low": valuation.get("low"),
            "base": valuation.get("base"),
            "high": valuation.get("high"),
            "note": "研究区间，不是目标价",
        }
    conclusion = _clean_agent_text(version.get("conclusion"))
    if not conclusion or "待补充" in conclusion:
        overall = _overall_score(dims)
        lead = next(
            (str(d.get("summary") or "") for d in dims if d.get("summary")),
            "六维分析已完成",
        )
        conclusion = f"六维平均得分 {overall}/10；{lead}" if overall is not None else lead
    summary = _clip_brief(conclusion)
    return _ensure_chief_memo_fields(
        {
            "summary": summary,
            "conclusion": summary,
            "decision": "watch",
            "six_dim_scores": [],
            "conflicts": [],
            "key_variables": questions[:3],
            "evidence": [],
            "risks": [_clip_brief(x) for x in _normalize_text_list(risks)],
            "open_questions": [_clip_brief(x) for x in _normalize_text_list(questions)],
            "price_range": price_range,
            "holding_period": "1-3 年（论点成立前提下，按季复核）",
            "engine": "rule",
        },
        version,
        case,
    )


def _apply_memo_data_gate(data: dict[str, Any], version: dict[str, Any]) -> dict[str, Any]:
    gates: dict[str, str] = {}
    for dim in version.get("six_dim") or []:
        if isinstance(dim, dict) and dim.get("key") and dim.get("gate"):
            gates[str(dim["key"])] = str(dim["gate"])
    industry = version.get("industry_analysis") or {}
    if isinstance(industry, dict) and industry.get("gate"):
        gates["industry"] = str(industry["gate"])
    if not gates:
        return data
    data["data_gates"] = gates
    labels = {str(d.get("key")): str(d.get("title") or d.get("key")) for d in version.get("six_dim") or [] if isinstance(d, dict)}
    labels["industry"] = "行业分析"
    failed = [labels.get(key, key) for key, gate in gates.items() if gate == "fail"]
    watched = [labels.get(key, key) for key, gate in gates.items() if gate == "watch"]
    decision = str(data.get("decision") or "")
    if decision == "proceed" and failed:
        data["decision_original"] = decision
        data["decision"] = "watch"
        data["decision_note"] = (
            "一页纸原判为进入下一步研究，但存在 gate=fail 的阻断维，服务端降级为观察。"
            f"阻断维：{'、'.join(failed)}。"
        )
        data["data_gate_note"] = data["decision_note"]
    elif failed:
        data["data_gate_note"] = (
            f"以下维度门禁未通过（gate=fail），按不可买入处理：{'、'.join(failed)}。"
        )
    elif watched:
        data["data_gate_note"] = (
            f"以下维度为 watch，已计入置信度，不阻断一页纸结论：{'、'.join(watched)}。"
            "免费数据未覆盖的行业空间/份额、护城河持续性与治理深度仍属未验证项。"
        )
    return data


def _sync_research_conclusion(org_id: int, version_id: int, memo: dict[str, Any]) -> None:
    """一页纸落库后，把同一段结论写回研究版本 conclusion，供 04 三关读取。"""
    conclusion = str(memo.get("conclusion") or memo.get("summary") or "").strip()
    if not conclusion:
        return
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, locked_at FROM inst_research_version WHERE id=%s AND case_id IN "
            "(SELECT id FROM inst_research_case WHERE org_id=%s)",
            (version_id, org_id),
        ).fetchone()
        if not row or row.get("locked_at") or str(row.get("status")) != "pending_review":
            return
        conn.execute(
            "UPDATE inst_research_version SET conclusion=%s, content_hash=NULL WHERE id=%s AND conclusion IS DISTINCT FROM %s",
            (conclusion[:2000], version_id, conclusion[:2000]),
        )


def ai_research_memo(
    org_id: int,
    case_id: int,
    *,
    refresh: bool = False,
    generate: bool = True,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    case = get_case(org_id, case_id)
    if not case:
        raise LookupError("研究案不存在")
    version = (case.get("versions") or [{}])[0]
    overall = _overall_score(version.get("six_dim") or [])
    if not version.get("id"):
        if not generate:
            return {
                "memo": None,
                "task": "inst.research_memo",
                "cached": True,
                "missing": True,
            }
        raise LookupError("还没有研究版本")
    payload = {
        "company": {k: case.get(k) for k in ("symbol", "company_name", "market", "industry", "ref_price")},
        "version": {
            "version_no": version.get("version_no"),
            "status": version.get("status"),
            "conclusion": version.get("conclusion"),
            "valuation": version.get("valuation"),
            "six_dim": version.get("six_dim"),
            "industry_analysis": version.get("industry_analysis"),
        },
        "evidence": [
            {"id": e.get("id"), "title": e.get("title"), "quote": e.get("quote"), "source": e.get("source"), "as_of": e.get("as_of")}
            for e in (case.get("evidence") or [])
        ],
    }
    prompt, prompt_version = get_effective_prompt("inst.research_memo", RESEARCH_MEMO_PROMPT)
    scope_key = f"case:{case_id}:version:{version.get('id')}"
    cache_key = agent_input_hash(
        {"case_id": case_id, "version_id": version.get("id"), "content_hash": version.get("content_hash"), "payload": payload},
        prompt,
    )
    if not refresh:
        hit = get_cached_output(
            "inst.research_memo",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
        )
        stale = False
        if hit and not _is_chief_output(hit.get("output")):
            hit = None
        if not hit:
            latest = get_latest_output("inst.research_memo", org_id=org_id, scope_key=scope_key)
            if latest and _is_chief_output(latest.get("output")):
                hit = latest
                stale = True
        if hit:
            memo = _ensure_chief_memo_fields(dict(hit["output"]), version, case)
            memo = _apply_memo_data_gate(memo, version)
            for field in ("risks", "open_questions", "key_variables"):
                if memo.get(field):
                    memo[field] = _normalize_text_list(memo[field])
            if not (isinstance(memo.get("metrics"), list) and len(memo.get("metrics") or []) >= 2):
                memo["metrics"] = _memo_metrics(case)
            memo = _merge_memo_metrics(memo, version, case)
            memo["overall_score"] = overall
            _sync_research_conclusion(org_id, int(version["id"]), memo)
            return {
                "memo": memo,
                "task": "inst.research_memo",
                "version_no": version.get("version_no"),
                "cached": True,
                "stale": stale,
                "generated_at": hit.get("created_at"),
            }
    if not generate:
        return {
            "memo": None,
            "task": "inst.research_memo",
            "version_no": version.get("version_no"),
            "cached": False,
            "missing": True,
        }
    try:
        data = _ai_task("inst.research_memo", payload, prompt)
        data.setdefault("engine", "agent")
        data = _ensure_chief_memo_fields(data, version, case)
    except AiUnavailable:
        # AI 未配置时仍给出一页纸骨架，内容全部来自六维规则结果。
        data = _rule_memo(version, case)
    data = _apply_memo_data_gate(data, version)
    for field in ("risks", "open_questions", "key_variables"):
        if data.get(field):
            data[field] = _normalize_text_list(data[field])
    metrics = data.get("metrics")
    if not (isinstance(metrics, list) and len(metrics) >= 2):
        data["metrics"] = _memo_metrics(case)
    data = _merge_memo_metrics(data, version, case)
    data["overall_score"] = overall
    _sync_research_conclusion(org_id, int(version["id"]), data)
    # 规则兜底也落盘：避免 AI 暂不可用时每次进入页面都重新生成。
    save_output(
        "inst.research_memo",
        org_id=org_id,
        scope_key=scope_key,
        input_hash=cache_key,
        prompt_version=prompt_version,
        output=data,
        engine=str(data.get("engine") or "agent"),
        created_by=actor_member_id,
    )
    return {
        "memo": data,
        "task": "inst.research_memo",
        "version_no": version.get("version_no"),
        "cached": False,
    }


def ai_dimension_chat_history(
    org_id: int,
    case_id: int,
    key: str,
    *,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    user_id = inst_ai_store.member_user_id(org_id, actor_member_id)
    items = (
        inst_ai_store.list_messages(org_id, case_id, key, user_id, limit=50)
        if user_id
        else []
    )
    return {"items": items}


def ai_dimension_chat(
    org_id: int,
    case_id: int,
    key: str,
    *,
    question: str,
    history: list[dict[str, Any]] | None = None,
    actor_member_id: int | None = None,
    client_message_id: str | None = None,
) -> dict[str, Any]:
    """单维追问：只带该维结论、证据与最近对话，不改业务状态。"""
    q = str(question or "").strip()
    if not q:
        raise ValueError("问题不能为空")
    dim_keys = {d[0] for d in SIX_DIM_DEFS}
    if key not in dim_keys:
        raise ValueError("未知研究维度")
    case = get_case(org_id, case_id)
    if not case:
        raise LookupError("研究案不存在")
    version = (case.get("versions") or [{}])[0]
    dims = [d for d in (version.get("six_dim") or []) if isinstance(d, dict)]
    dim = next((d for d in dims if d.get("key") == key), None)
    if not dim:
        raise LookupError("该维度尚未生成")
    ev_ids = {int(x) for x in (dim.get("evidence_ids") or []) if str(x).isdigit()}
    evidence = [e for e in (case.get("evidence") or []) if int(e.get("id") or 0) in ev_ids]
    user_id = inst_ai_store.member_user_id(org_id, actor_member_id)
    stored = (
        inst_ai_store.list_messages(org_id, case_id, key, user_id, limit=50)
        if user_id
        else []
    )
    history_source = stored[-8:] if stored else (history or [])[-8:]
    history_in: list[dict[str, str]] = []
    for item in history_source:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            history_in.append({"role": role, "content": content[:2000]})
    payload = {
        "company": {k: case.get(k) for k in ("symbol", "company_name", "market", "industry", "ref_price")},
        "dimension": {
            k: dim.get(k)
            for k in (
                "key",
                "title",
                "question",
                "summary",
                "checks",
                "counter",
                "open_questions",
                "data_gaps",
                "confidence",
                "engine",
            )
        },
        "evidence": [
            {"id": e.get("id"), "title": e.get("title"), "quote": e.get("quote"), "source": e.get("source")}
            for e in evidence
        ],
        "history": history_in,
        "question": q[:2000],
    }
    data = _ai_task("inst.dim.chat", payload, CHAT_PROMPT)
    answer = str(data.get("answer") or data.get("summary") or "").strip()
    if not answer:
        raise AiUnavailable("AI 未返回内容")
    if user_id:
        inst_ai_store.append_message(
            org_id, case_id, key, user_id,
            member_id=actor_member_id, role="user", content=q,
            client_message_id=client_message_id,
        )
        inst_ai_store.append_message(
            org_id, case_id, key, user_id,
            member_id=actor_member_id, role="assistant", content=answer,
            client_message_id=f"{client_message_id}:a" if client_message_id else None,
        )
    with get_conn() as conn:
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="research.dimension.chat",
            object_type="inst_research_version",
            object_id=int(version.get("id") or 0),
            after={"case_id": case_id, "key": key, "question": q[:200], "answer": answer[:300]},
        )
    return {
        "answer": answer,
        "dimension": key,
        "task": "inst.dim.chat",
        "engine": str(data.get("engine") or "agent"),
    }


def ai_partner_memo(
    org_id: int,
    proposal_id: int,
    *,
    refresh: bool = False,
    actor_member_id: int | None = None,
    cached_only: bool = False,
) -> dict[str, Any]:
    """合伙人审批建议：只给合伙人本人看，独立于其他合伙人意见。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "partner")
    proposal = get_proposal(org_id, proposal_id)
    if not proposal:
        raise LookupError("议案不存在")
    version = proposal.get("current_version") or {}
    research = None
    if proposal.get("case_id"):
        with get_conn() as conn:
            research = _research_debate_summary(conn, org_id, int(proposal["case_id"]))
    pf = portfolio(org_id)
    payload = {
        "proposal": {
            k: proposal.get(k)
            for k in (
                "id", "status", "direction", "target_weight", "symbol", "company_name",
                "market", "industry",
            )
        },
        "version": {"version_no": version.get("version_no"), "snapshot": version.get("snapshot")},
        "research_debate": research,
        "portfolio": {
            "nav": pf.get("nav"),
            "cash": pf.get("cash"),
            "invested_ratio": pf.get("invested_ratio"),
            "positions": [
                {
                    k: pos.get(k)
                    for k in ("symbol", "name", "industry", "qty", "cost", "weight")
                }
                for pos in (pf.get("positions") or [])
            ],
        },
    }
    prompt, prompt_version = get_effective_prompt("inst.partner_memo", PARTNER_MEMO_PROMPT)
    scope_key = f"proposal:{proposal_id}:version:{version.get('id')}:task:partner"
    cache_key = agent_input_hash(payload, prompt)
    if not refresh:
        hit = get_cached_output(
            "inst.partner_memo",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
        )
        stale = False
        if not hit:
            hit = get_latest_output("inst.partner_memo", org_id=org_id, scope_key=scope_key)
            stale = bool(hit)
        if hit:
            return {
                "memo": hit["output"],
                "task": "inst.partner_memo",
                "version_no": version.get("version_no"),
                "cached": True,
                "stale": stale,
                "generated_at": hit.get("created_at"),
            }
    if cached_only:
        return {
            "memo": None,
            "task": "inst.partner_memo",
            "version_no": version.get("version_no"),
            "cached": True,
            "missing": True,
        }
    data = _ai_task("inst.partner_memo", payload, prompt)
    data.setdefault("engine", "agent")
    save_output(
        "inst.partner_memo",
        org_id=org_id,
        scope_key=scope_key,
        input_hash=cache_key,
        prompt_version=prompt_version,
        output=data,
        engine=str(data.get("engine") or "agent"),
        created_by=actor_member_id,
    )
    return {
        "memo": data,
        "task": "inst.partner_memo",
        "version_no": version.get("version_no"),
        "cached": False,
    }


def ai_risk_review(
    org_id: int,
    proposal_id: int,
    *,
    refresh: bool = False,
    actor_member_id: int | None = None,
    cached_only: bool = False,
) -> dict[str, Any]:
    proposal = get_proposal(org_id, proposal_id)
    if not proposal:
        raise LookupError("议案不存在")
    version = proposal.get("current_version") or {}
    payload = {
        "proposal": {k: proposal.get(k) for k in ("id", "status", "direction", "target_weight", "symbol", "company_name")},
        "version": {"version_no": version.get("version_no"), "snapshot": version.get("snapshot")},
        "checks": None,
        "policy": {"max_single_weight": MAX_SINGLE_WEIGHT, "min_cash_ratio": MIN_CASH_RATIO, "policy_version": POLICY_VERSION},
    }
    # 用真实检查项；避免在 AI 侧重算。
    with get_conn() as conn:
        proposal_row = _proposal_row(conn, org_id, proposal_id)
        current = _current_version(conn, proposal_id)
        checks = _risk_checks(conn, org_id, proposal_row or proposal, current or version)
    payload["checks"] = checks
    prompt, prompt_version = get_effective_prompt("inst.risk_review", RISK_REVIEW_PROMPT)
    scope_key = f"proposal:{proposal_id}:version:{(current or version).get('id')}:task:risk"
    cache_key = agent_input_hash(payload, prompt)
    if not refresh:
        hit = get_cached_output(
            "inst.risk_review",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
        )
        stale = False
        if not hit:
            hit = get_latest_output("inst.risk_review", org_id=org_id, scope_key=scope_key)
            stale = bool(hit)
        if hit:
            return {
                "memo": hit["output"],
                "task": "inst.risk_review",
                "checks": checks,
                "cached": True,
                "stale": stale,
                "generated_at": hit.get("created_at"),
            }
    if cached_only:
        return {
            "memo": None,
            "task": "inst.risk_review",
            "checks": checks,
            "cached": True,
            "missing": True,
        }
    data = _ai_task("inst.risk_review", payload, prompt)
    data.setdefault("engine", "agent")
    if data.get("engine") != "rule":
        save_output(
            "inst.risk_review",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
            output=data,
            engine=str(data.get("engine") or "agent"),
            created_by=actor_member_id,
        )
    return {"memo": data, "task": "inst.risk_review", "checks": checks, "cached": False}


def ai_chairman_memo(
    org_id: int,
    proposal_id: int,
    *,
    refresh: bool = False,
    actor_member_id: int | None = None,
    cached_only: bool = False,
) -> dict[str, Any]:
    proposal = get_proposal(org_id, proposal_id)
    if not proposal:
        raise LookupError("议案不存在")
    version = proposal.get("current_version") or {}
    payload = {
        "proposal": {k: proposal.get(k) for k in ("id", "status", "direction", "target_weight", "symbol", "company_name")},
        "version": {"version_no": version.get("version_no"), "snapshot": version.get("snapshot")},
        "approvals": proposal.get("approvals") or [],
        "authorizations": proposal.get("authorizations") or [],
        "policy": {"max_single_weight": MAX_SINGLE_WEIGHT, "min_cash_ratio": MIN_CASH_RATIO, "policy_version": POLICY_VERSION},
    }
    prompt, prompt_version = get_effective_prompt("inst.chairman_memo", CHAIRMAN_MEMO_PROMPT)
    scope_key = f"proposal:{proposal_id}:version:{version.get('id')}:task:chairman"
    cache_key = agent_input_hash(payload, prompt)
    if not refresh:
        hit = get_cached_output(
            "inst.chairman_memo",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
        )
        stale = False
        if not hit:
            hit = get_latest_output("inst.chairman_memo", org_id=org_id, scope_key=scope_key)
            stale = bool(hit)
        if hit:
            return {
                "memo": hit["output"],
                "task": "inst.chairman_memo",
                "version_no": version.get("version_no"),
                "cached": True,
                "stale": stale,
                "generated_at": hit.get("created_at"),
            }
    if cached_only:
        return {
            "memo": None,
            "task": "inst.chairman_memo",
            "version_no": version.get("version_no"),
            "cached": True,
            "missing": True,
        }
    data = _ai_task("inst.chairman_memo", payload, prompt)
    data.setdefault("engine", "agent")
    if data.get("engine") != "rule":
        save_output(
            "inst.chairman_memo",
            org_id=org_id,
            scope_key=scope_key,
            input_hash=cache_key,
            prompt_version=prompt_version,
            output=data,
            engine=str(data.get("engine") or "agent"),
            created_by=actor_member_id,
        )
    return {"memo": data, "task": "inst.chairman_memo", "version_no": version.get("version_no"), "cached": False}


def _ai_available(task_id: str = "inst.chairman_memo") -> bool:
    try:
        from ai.router import available_task

        return bool(available_task(task_id))
    except Exception:
        return False


def _chairman_context(
    org_id: int, proposal_id: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], int]:
    with get_conn() as conn:
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        current = _current_version(conn, proposal_id)
        if not current:
            raise LookupError("议案版本不存在")
        rows = _approval_rows(conn, int(current["id"]))
        state = _approval_state(rows, _member_role_counts(conn, org_id))

        def _summary(step: str, passed_decisions: set[str]) -> dict[str, Any]:
            item = state[step]
            decisions = [str(r.get("decision") or "") for r in item["items"]]
            if "conditional" in decisions:
                decision = "conditional"
            elif item["passed"]:
                decision = next((d for d in decisions if d in passed_decisions), "approve")
            elif item["vetoed"]:
                decision = "veto"
            else:
                decision = item["latest"].get("decision") if item["latest"] else None
            return {
                "step": step,
                "decision": decision,
                "passed": item["passed"],
                "vetoed": item["vetoed"],
                "conditions": item["conditions"],
            }

        approvals = {
            "partner": _summary("partner", {"approve", "conditional"}),
            "risk_precheck": _summary("risk_precheck", {"pass", "conditional"}),
            "chairman": _summary("chairman", {"approve", "conditional"}),
        }
        snapshot = current.get("snapshot") or {}
        risk_checks = _risk_checks(conn, org_id, proposal, current)
        evidence_count = 0
        research_version_id = snapshot.get("research_version_id")
        if research_version_id:
            row = conn.execute(
                "SELECT evidence_ids FROM inst_research_version WHERE id=%s",
                (research_version_id,),
            ).fetchone()
            if row:
                evidence_count = len(row.get("evidence_ids") or [])
    return proposal, current, snapshot, approvals, risk_checks, evidence_count


def ai_chairman_precheck(
    org_id: int, proposal_id: int, *, actor_member_id: int | None = None
) -> dict[str, Any]:
    """预检查：只读，不改状态。"""
    from services.institution.chairman_mode import evaluate

    proposal, current, snapshot, approvals, risk_checks, evidence_count = _chairman_context(
        org_id, proposal_id
    )
    result = evaluate(
        proposal_status=str(proposal.get("status") or ""),
        snapshot=snapshot,
        approvals=approvals,
        risk_checks=risk_checks,
        evidence_count=evidence_count,
        ai_available=_ai_available(),
        proposer_is_reviewer=int(proposal.get("created_by") or 0) == int(actor_member_id or 0),
    )
    result.update(
        {
            "proposal_id": proposal_id,
            "version_no": current.get("version_no"),
            "status": proposal.get("status"),
        }
    )
    return result


def ai_chairman_simulate(
    org_id: int, proposal_id: int, *, actor_member_id: int | None = None
) -> dict[str, Any]:
    """模拟批准：只记录建议与审计，不写审批、不改状态。"""
    pre = ai_chairman_precheck(org_id, proposal_id, actor_member_id=actor_member_id)
    memo = None
    if _ai_available():
        try:
            memo = ai_chairman_memo(org_id, proposal_id).get("memo")
        except AiUnavailable:
            memo = None
    recommendation = pre["recommendation"]
    decision = {
        "approve_candidate": "approve",
        "conditional_candidate": "conditional",
    }.get(recommendation, "handover")
    with get_conn() as conn:
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.chairman.ai_simulate",
            object_type="inst_proposal",
            object_id=proposal_id,
            after={
                "simulated_decision": decision,
                "blocking": pre["blocking"],
                "warnings": pre["warnings"],
                "binding": False,
            },
        )
    return {
        **pre,
        "mode": "ai_simulated",
        "simulated_decision": decision,
        "memo": memo,
        "note": "AI 模拟结果不构成批准；需真人 Chairman 表决",
    }


def ai_chairman_handover(
    org_id: int,
    proposal_id: int,
    *,
    actor_member_id: int | None,
    note: str | None = None,
) -> dict[str, Any]:
    """人工移交：Chairman 放弃 AI 模拟，转真人流程；只写审计。"""
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "chairman")
        proposal = _proposal_row(conn, org_id, proposal_id)
        if not proposal:
            raise LookupError("议案不存在")
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="proposal.chairman.ai_handover",
            object_type="inst_proposal",
            object_id=proposal_id,
            after={"note": note or "已移交真人 Chairman", "status": proposal.get("status")},
        )
    return {
        "ok": True,
        "handover": True,
        "proposal_id": proposal_id,
        "status": proposal.get("status"),
        "note": note or "已移交真人 Chairman",
    }


def list_audit(org_id: int, limit: int = 100) -> list[dict[str, Any]]:
    return repo.audit(OrgScope(org_id), limit=limit)


__all__ = [
    "AiUnavailable",
    "DEMO_COMPANIES",
    "POLICY_VERSION",
    "ai_chairman_memo",
    "ai_research_memo",
    "ai_risk_review",
    "approve_and_execute",
    "authorize",
    "chairman_review",
    "create_case",
    "create_exit_case",
    "create_monitor_event",
    "create_proposal",
    "ensure_and_seed",
    "execute_authorization",
    "generate_research",
    "get_case",
    "get_company",
    "get_debate",
    "get_proposal",
    "ideas_push",
    "list_audit",
    "list_authorizations",
    "list_cases",
    "list_companies",
    "list_proposals",
    "monitor",
    "overview",
    "partner_review",
    "portfolio",
    "review_research",
    "risk_check",
    "start_debate",
    "update_company_pool",
]


def institution_agent_catalog(org_id: int, *, can_edit: bool) -> dict[str, Any]:
    """机构 Agent 管理目录：只返回主观机构端自己的 Agent；仅经理可看提示词正文。"""
    from services.ai_agents import catalog as agent_catalog

    items = [
        item
        for item in agent_catalog.list_agents(include_prompt=can_edit)
        if item.get("source") == "institution"
    ]
    return {
        "items": items,
        "count": len(items),
        "editable_count": sum(1 for item in items if item.get("editable")),
        "can_edit": can_edit,
    }


def save_institution_agent_prompt(
    org_id: int,
    task_id: str,
    prompt: str,
    *,
    note: str | None,
    actor_member_id: int | None,
) -> dict[str, Any]:
    from services.ai_agents import catalog as agent_catalog

    if not agent_catalog.is_editable_institution(task_id):
        raise ValueError("该 Agent 暂未接入提示词管理")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        result = agent_store.save_prompt(
            task_id, prompt, updated_by=actor_member_id, note=note
        )
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="agent.prompt.save",
            object_type="ai_agent_prompt",
            object_id=0,
            after={"task_id": task_id, "version": result["version"], "prompt_hash": result["prompt_hash"]},
        )
    result["agent"] = agent_catalog.get_agent(task_id, include_prompt=True)
    return result


def reset_institution_agent_prompt(
    org_id: int,
    task_id: str,
    *,
    actor_member_id: int | None,
) -> dict[str, Any]:
    from services.ai_agents import catalog as agent_catalog

    if not agent_catalog.is_editable_institution(task_id):
        raise ValueError("该 Agent 暂未接入提示词管理")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
        result = agent_store.reset_prompt(task_id, updated_by=actor_member_id)
        _audit(
            conn,
            org_id=org_id,
            actor_member_id=actor_member_id,
            action="agent.prompt.reset",
            object_type="ai_agent_prompt",
            object_id=0,
            after={"task_id": task_id, "version": result["version"]},
        )
    result["agent"] = agent_catalog.get_agent(task_id, include_prompt=True)
    return result


def institution_agent_prompt_history(
    org_id: int,
    task_id: str,
    *,
    actor_member_id: int | None,
) -> dict[str, Any]:
    from services.ai_agents import catalog as agent_catalog

    if not agent_catalog.is_editable_institution(task_id):
        raise ValueError("该 Agent 暂未接入提示词管理")
    with get_conn() as conn:
        member = _member(conn, org_id, actor_member_id)
        _require_role(member, "manager")
    return {
        "items": agent_store.list_prompt_history(task_id),
        "agent": agent_catalog.get_agent(task_id, include_prompt=True),
    }


def ai_role_catalog() -> list[dict[str, Any]]:
    out = []
    for key, label, task in AI_ROLE_CATALOG:
        out.append(
            {
                "key": key,
                "label": label,
                "task": task,
                "available": _ai_available(task),
            }
        )
    return out


def _role_case_payload(org_id: int, case_id: int) -> dict[str, Any]:
    data = get_case(org_id, case_id)
    if not data:
        raise LookupError("研究案不存在")
    version = (data.get("versions") or [None])[0] or {}
    return {
        "company": {
            "symbol": data.get("symbol"),
            "name": data.get("company_name"),
            "market": data.get("market"),
            "industry": data.get("industry"),
            "data_status": data.get("data_status"),
        },
        "research": {
            "version_no": version.get("version_no"),
            "status": version.get("status"),
            "conclusion": version.get("conclusion"),
            "six_dim": [
                {
                    "key": d.get("key"),
                    "title": d.get("title"),
                    "summary": d.get("summary"),
                    "counter": d.get("counter"),
                }
                for d in (version.get("six_dim") or [])
            ],
            "valuation": version.get("valuation"),
            "counter_evidence": version.get("counter_evidence"),
            "open_questions": version.get("open_questions"),
        },
        "evidence": [
            {"id": e.get("id"), "title": e.get("title"), "source": e.get("source"), "quote": e.get("quote")}
            for e in (data.get("evidence") or [])[:30]
        ],
    }


def ai_role_run(
    org_id: int,
    role_key: str,
    *,
    case_id: int | None = None,
    proposal_id: int | None = None,
    actor_member_id: int | None = None,
) -> dict[str, Any]:
    """执行一个 AI 岗位：只输出建议，不改业务状态。"""
    role = str(role_key or "").strip().lower()
    task = {key: task_id for key, _label, task_id in AI_ROLE_CATALOG}.get(role)
    if not task:
        raise ValueError("未知 AI 岗位")
    if role == "debate":
        if not case_id:
            raise ValueError("缺少 case_id")
        return {"role": role, "task": task, "result": start_debate(org_id, case_id, actor_member_id=actor_member_id, use_ai=True)}
    if role == "risk":
        if not proposal_id:
            raise ValueError("缺少 proposal_id")
        return {"role": role, "task": task, "result": ai_risk_review(org_id, proposal_id)}
    if role == "research":
        if not case_id:
            raise ValueError("缺少 case_id")
        return {"role": role, "task": task, "result": ai_research_memo(org_id, case_id)}
    if not case_id:
        raise ValueError("缺少 case_id")
    payload = _role_case_payload(org_id, case_id)
    data = _ai_task(task, payload, _ROLE_PROMPTS[role])
    return {"role": role, "task": task, "memo": data}
AI_ROLE_CATALOG: tuple[tuple[str, str, str], ...] = (
    ("research", "研究统筹 / 产业 / 护城河", "inst.research_memo"),
    ("financial", "财务与取证", "inst.role.financial"),
    ("governance", "治理 / 估值 / 反证", "inst.role.governance"),
    ("debate", "看多 / 看空 / 主持", "inst.debate"),
    ("risk", "风控 / 合规 / 交易", "inst.risk_review"),
    ("post_investment", "投后 / 退出 / 复盘", "inst.role.post_investment"),
)
