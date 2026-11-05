# -*- coding: utf-8 -*-
"""主观机构端 AI 任务（ADR-037 TaskSpec）。

原则：
- AI 只出建议，不改业务状态；所有重大结论必须绑定 evidence id。
- 不给买卖点、目标价、收益承诺；不绕过风控与审批。
- 输出统一 JSON，校验失败抛 AiBadOutput，由路由层映射 502。
"""
from __future__ import annotations

import json
from typing import Any

from ai.errors import AiBadOutput
from ai.router.specs import TaskRequest, TaskSpec, register

PROMPT_VERSION = "inst-v2"
DIM_PROMPT_VERSION = "inst-dim-v2"
BRIEF_MAX_CHARS = 50


def clip_brief(value: Any) -> str:
    """摘要/结论字段上限 50 字；超长时保留前 49 字 + 省略号。"""
    text = " ".join(str(value or "").split())
    if len(text) <= BRIEF_MAX_CHARS:
        return text
    return text[: BRIEF_MAX_CHARS - 1] + "…"


def _strip(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


def _load(raw: str) -> dict[str, Any]:
    text = _strip(raw)
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, IndexError, ValueError) as exc:
        raise AiBadOutput("机构端 AI 返回不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise AiBadOutput("机构端 AI 返回不是 JSON 对象")
    return data


def validate_debate(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    valid_ids = {int(x) for x in (request.variables.get("evidence_ids") or []) if str(x).isdigit()}
    for side in ("bull", "bear", "chair"):
        items = data.get(side)
        if not isinstance(items, list) or not items:
            raise AiBadOutput(f"辩论缺少 {side} 论点")
        for item in items:
            if not isinstance(item, dict) or not str(item.get("claim") or "").strip():
                raise AiBadOutput(f"{side} 论点缺少 claim")
            ids = []
            for x in item.get("evidence_ids") or []:
                try:
                    v = int(x)
                except (TypeError, ValueError):
                    continue
                if v in valid_ids:
                    ids.append(v)
            item["evidence_ids"] = ids
            item.setdefault("confidence", 0.5)
            item.setdefault("round", 1)
        data[side] = items
    return data


def validate_dimension(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    if not str(data.get("summary") or "").strip():
        raise AiBadOutput("六维 Agent 缺少 summary")
    data["summary"] = clip_brief(data.get("summary"))
    for key in ("checks", "counter", "open_questions", "data_gaps"):
        value = data.get(key)
        data[key] = [clip_brief(x) for x in value if str(x).strip()] if isinstance(value, list) else []
    items = data.get("evidence")
    evidence = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if not title or not quote:
            continue
        evidence.append(
            {
                "title": title[:200],
                "quote": quote[:500],
                "source": str(item.get("source") or "agent").strip()[:80],
            }
        )
    data["evidence"] = evidence
    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.5
    data["confidence"] = max(0.0, min(1.0, confidence))
    return data


def validate_memo(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    for key in ("summary", "evidence", "risks", "open_questions"):
        value = data.get(key)
        if value is None:
            data[key] = [] if key != "summary" else ""
    data["summary"] = clip_brief(data.get("summary"))
    for key in ("evidence", "risks", "open_questions"):
        value = data.get(key)
        data[key] = [clip_brief(x) for x in value if str(x).strip()] if isinstance(value, list) else []
    return data


DIMENSION_KEYS = {"industry", "business_model", "moat", "financial", "governance", "valuation"}


def validate_research_memo(raw: str, request: TaskRequest) -> dict[str, Any]:
    """CIO 一页纸：保留摘要字段，并校验研究建议与六维评分。"""
    data = validate_memo(raw, request)
    decision = str(data.get("decision") or "").strip().lower()
    data["decision"] = decision if decision in {"proceed", "watch", "avoid"} else "watch"

    scores = []
    for item in data.get("six_dim_scores") if isinstance(data.get("six_dim_scores"), list) else []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key not in DIMENSION_KEYS:
            continue
        try:
            score = float(item.get("score"))
        except (TypeError, ValueError):
            continue
        if not 1 <= score <= 5:
            continue
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.5
        scores.append(
            {
                "key": key,
                "score": round(score, 1),
                "confidence": max(0.0, min(1.0, confidence)),
                "note": str(item.get("note") or "")[:200],
            }
        )
    data["six_dim_scores"] = scores
    for item in scores:
        item["note"] = clip_brief(item.get("note"))
    for key in ("conflicts", "key_variables"):
        value = data.get(key)
        data[key] = [clip_brief(x) for x in value if str(x).strip()] if isinstance(value, list) else []
    raw_range = data.get("price_range")
    if isinstance(raw_range, dict):
        price_range = {}
        for key in ("low", "base", "high"):
            try:
                value = float(raw_range.get(key))
            except (TypeError, ValueError):
                value = None
            price_range[key] = value
        price_range["note"] = clip_brief(raw_range.get("note") or "研究区间，不是目标价")
        data["price_range"] = price_range if any(price_range.get(k) is not None for k in ("low", "base", "high")) else None
    else:
        data["price_range"] = None
    data["holding_period"] = clip_brief(data.get("holding_period"))
    return data


def validate_chat(raw: str, request: TaskRequest) -> dict[str, Any]:
    """单维对话：接受 JSON {"answer": ...} 或纯文本。"""
    text = _strip(raw)
    if not text:
        raise AiBadOutput("机构端对话返回为空")
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            data = None
        if isinstance(data, dict):
            answer = str(data.get("answer") or data.get("content") or "").strip()
            if answer:
                return {"answer": answer[:4000]}
    return {"answer": text[:4000]}


DEBATE_TASK = register(
    TaskSpec(
        task_id="inst.debate",
        description="机构端投资辩论：正/反/主持三段论证，必须引用 evidence id",
        temperature=0.3,
        max_tokens=4000,
        timeout_sec=150,
        executors=("local",),
        validator=validate_debate,
    )
)

INDUSTRY_TASK = register(
    TaskSpec(
        task_id="inst.industry",
        description="机构端独立行业分析：空间、周期、产业链、竞争格局与政策",
        temperature=0.2,
        max_tokens=3000,
        timeout_sec=120,
        executors=("local",),
        response_format={"type": "json_object"},
        validator=validate_dimension,
    )
)

RESEARCH_MEMO_TASK = register(
    TaskSpec(
        task_id="inst.research_memo",
        description="机构端 CIO 一页纸：研究建议、六维评分、矛盾、证据与待核验",
        temperature=0.3,
        max_tokens=3600,
        timeout_sec=120,
        executors=("local",),
        validator=validate_research_memo,
    )
)

DIMENSION_CHAT_TASK = register(
    TaskSpec(
        task_id="inst.dim.chat",
        description="机构端单维对话：围绕一个研究维度与证据回答追问",
        temperature=0.3,
        max_tokens=1500,
        timeout_sec=90,
        executors=("local",),
        validator=validate_chat,
    )
)

RISK_REVIEW_TASK = register(
    TaskSpec(
        task_id="inst.risk_review",
        description="机构端独立风控复核意见（只建议，不改变状态）",
        temperature=0.2,
        max_tokens=2500,
        timeout_sec=120,
        executors=("local",),
        validator=validate_memo,
    )
)

CHAIRMAN_MEMO_TASK = register(
    TaskSpec(
        task_id="inst.chairman_memo",
        description="机构端 Chairman 一页式决策摘要（不含目标价与买卖指令）",
        temperature=0.2,
        max_tokens=3000,
        timeout_sec=120,
        executors=("local",),
        validator=validate_memo,
    )
)

FINANCIAL_ROLE_TASK = register(
    TaskSpec(
        task_id="inst.role.financial",
        description="机构端 AI 岗位：财务与取证（三表勾稽、ROIC/FCF、应收存货与会计风险）",
        temperature=0.2,
        max_tokens=3000,
        timeout_sec=120,
        executors=("local",),
        validator=validate_memo,
    )
)

GOVERNANCE_ROLE_TASK = register(
    TaskSpec(
        task_id="inst.role.governance",
        description="机构端 AI 岗位：治理/估值/反证（资本配置、DCF 假设、可检验反证条件）",
        temperature=0.2,
        max_tokens=3000,
        timeout_sec=120,
        executors=("local",),
        validator=validate_memo,
    )
)

POST_INVESTMENT_ROLE_TASK = register(
    TaskSpec(
        task_id="inst.role.post_investment",
        description="机构端 AI 岗位：投后/退出/复盘（论点台账、经营预警、退出备忘录与归因）",
        temperature=0.2,
        max_tokens=3000,
        timeout_sec=120,
        executors=("local",),
        validator=validate_memo,
    )
)


DIMENSION_TASK_SPECS = {
    "industry": ("inst.dim.industry", "行业与产业 Agent：规模、竞争结构、供需与周期"),
    "business_model": ("inst.dim.business_model", "商业模式 Agent：收入结构、客户价值、单位经济性"),
    "moat": ("inst.dim.moat", "护城河 Agent：品牌、成本、网络、转换成本与侵蚀路径"),
    "financial": ("inst.dim.financial", "财务质量 Agent：三表勾稽、ROIC/FCF、会计风险"),
    "governance": ("inst.dim.governance", "治理 Agent：资本配置、承诺兑现、关联交易"),
    "valuation": ("inst.dim.valuation", "估值 Agent：PE/PB 分位、DCF 假设、安全边际"),
}

DIMENSION_TASKS = {}
for _key, (_task_id, _desc) in DIMENSION_TASK_SPECS.items():
    DIMENSION_TASKS[_key] = register(
        TaskSpec(
            task_id=_task_id,
            description=_desc,
            temperature=0.2,
            max_tokens=4096,
            timeout_sec=120,
            executors=("local",),
            response_format={"type": "json_object"},
            validator=validate_dimension,
        )
    )

__all__ = [
    "FINANCIAL_ROLE_TASK",
    "GOVERNANCE_ROLE_TASK",
    "POST_INVESTMENT_ROLE_TASK",
    "CHAIRMAN_MEMO_TASK",
    "DEBATE_TASK",
    "DIMENSION_CHAT_TASK",
    "PROMPT_VERSION",
    "RESEARCH_MEMO_TASK",
    "INDUSTRY_TASK",
    "RISK_REVIEW_TASK",
    "validate_debate",
    "DIMENSION_TASKS",
    "DIM_PROMPT_VERSION",
    "validate_dimension",
    "validate_memo",
    "validate_research_memo",
]
