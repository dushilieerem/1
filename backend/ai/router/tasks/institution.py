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

PROMPT_VERSION = "inst-v3"
DIM_PROMPT_VERSION = "inst-dim-v3"


def clip_brief(value: Any) -> str:
    """只做空白归一化，不再截断；完整保留 Agent 的结论与依据。"""
    return " ".join(str(value or "").split())


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


def _first_paragraph(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for part in text.split("\n\n"):
        part = part.strip()
        if part:
            return part
    return text


def _text(value: Any, *keys: str) -> str:
    if isinstance(value, dict):
        for key in keys:
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def validate_dimension(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    summary = str(data.get("summary") or "").strip()
    if not summary:
        summary = str(data.get("one_line") or "").strip() or _first_paragraph(data.get("analysis_md"))
    if not summary:
        raise AiBadOutput("六维 Agent 缺少 summary/one_line/analysis_md")
    data["summary"] = clip_brief(summary)

    checks: list[str] = []
    for item in data.get("key_numbers") or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            value = str(item.get("value") or "").strip()
            period = str(item.get("period") or "").strip()
            if name or value:
                checks.append(f"{name}：{value}" + (f"（{period}）" if period else ""))
        elif str(item).strip():
            checks.append(str(item))
    if not checks:
        checks = [clip_brief(x) for x in (data.get("checks") or []) if str(x).strip()]
    data["checks"] = checks[:8]

    counter: list[str] = []
    for item in data.get("falsifiers") or []:
        if isinstance(item, dict):
            text = "；".join(
                part
                for part in (
                    str(item.get("condition") or "").strip(),
                    f"阈值 {item.get('threshold')}" if item.get("threshold") not in (None, "") else "",
                    f"观察 {item.get('observe')}" if item.get("observe") else "",
                )
                if part
            )
            if text:
                counter.append(text)
        elif str(item).strip():
            counter.append(str(item))
    if not counter:
        counter = [clip_brief(x) for x in (data.get("counter") or []) if str(x).strip()]
    data["counter"] = counter[:6]

    gaps: list[str] = []
    for item in data.get("data_gaps") or []:
        if isinstance(item, dict):
            text = "；".join(
                part
                for part in (
                    str(item.get("item") or "").strip(),
                    f"影响 {item.get('impact')}" if item.get("impact") else "",
                    f"补数 {item.get('workaround')}" if item.get("workaround") else "",
                )
                if part
            )
            if text:
                gaps.append(text)
        elif str(item).strip():
            gaps.append(str(item))
    data["data_gaps"] = gaps[:10]

    open_questions = [clip_brief(x) for x in (data.get("open_questions") or []) if str(x).strip()]
    data["open_questions"] = (open_questions or gaps)[:6]

    evidence = []
    for item in data.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("document_id") or item.get("evidence_id") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if not title or not quote:
            continue
        recorded = {
            "title": title[:300],
            "quote": quote[:1500],
            "source": str(item.get("source") or item.get("grade") or "agent").strip()[:120],
        }
        if item.get("evidence_id") not in (None, ""):
            recorded["evidence_id"] = item.get("evidence_id")
        if item.get("grade"):
            recorded["grade"] = item.get("grade")
        evidence.append(recorded)
    data["evidence"] = evidence

    label = str(data.get("confidence") or "").strip().upper()
    if label in {"H", "M", "L"}:
        data["confidence_label"] = label
        data["confidence"] = {"H": 0.9, "M": 0.6, "L": 0.3}[label]
    else:
        try:
            confidence = float(data.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.5
        data["confidence"] = max(0.0, min(1.0, confidence))
    return data


def validate_memo(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    summary = data.get("summary")
    if not summary:
        summary = _first_paragraph(data.get("reason")) or _first_paragraph(data.get("memo_md"))
        summary = summary or str(data.get("verdict") or data.get("decision") or "")
    data["summary"] = clip_brief(summary)

    evidence = data.get("evidence")
    if not evidence:
        ids: list[str] = []
        for item in data.get("checks") or []:
            if isinstance(item, dict):
                ids.extend(str(x) for x in (item.get("evidence_ids") or []))
        evidence = ids
    data["evidence"] = [clip_brief(x) for x in evidence if str(x).strip()] if isinstance(evidence, list) else []

    risks = data.get("risks")
    if not risks:
        derived: list[str] = []
        for item in data.get("checks") or []:
            if isinstance(item, dict):
                status = str(item.get("status") or "").lower()
                failed = item.get("pass") is False or status in {"warn", "block", "fail", "veto"}
                if failed:
                    label = _text(item, "item", "label", "name")
                    detail = _text(item, "detail", "note", "reason")
                    derived.append(f"{label}：{detail}" if label and detail else label or detail)
        risks = [x for x in derived if x]
    data["risks"] = [clip_brief(x) for x in risks if str(x).strip()] if isinstance(risks, list) else []

    open_questions = data.get("open_questions")
    if not open_questions:
        derived = []
        for cond in data.get("conditions") or []:
            text = _text(cond, "text", "condition", "detail")
            if text:
                derived.append(text)
        for item in data.get("unresolved") or []:
            text = _text(item, "issue", "text", "detail")
            if text:
                derived.append(text)
        open_questions = derived
    data["open_questions"] = (
        [clip_brief(x) for x in open_questions if str(x).strip()] if isinstance(open_questions, list) else []
    )
    return data


DIMENSION_KEYS = {"industry", "business_model", "moat", "financial", "governance", "valuation"}
DIMENSION_ALIASES = {
    "industry_position": "industry",
    "industry": "industry",
    "产业研究": "industry",
    "商业与产业": "industry",
    "business_model": "business_model",
    "商业模式": "business_model",
    "moat": "moat",
    "护城河": "moat",
    "financial": "financial",
    "财务质量": "financial",
    "governance": "governance",
    "治理": "governance",
    "valuation": "valuation",
    "估值": "valuation",
}


def _confidence_number(value: Any) -> float:
    if isinstance(value, str) and value.strip().upper() in {"H", "M", "L"}:
        return {"H": 0.9, "M": 0.6, "L": 0.3}[value.strip().upper()]
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def validate_research_memo(raw: str, request: TaskRequest) -> dict[str, Any]:
    """CIO 一页纸：兼容 A10 契约（dimension_scores/price_band/memo_md）与旧字段。"""
    data = validate_memo(raw, request)
    sentences = data.get("three_sentences")
    if isinstance(sentences, dict):
        combined = "；".join(
            part
            for part in (
                str(sentences.get("decision") or "").strip(),
                str(sentences.get("thesis") or "").strip(),
            )
            if part
        )
        if combined:
            data["summary"] = clip_brief(combined)
    if not data.get("summary"):
        if isinstance(sentences, dict):
            data["summary"] = clip_brief(sentences.get("decision") or sentences.get("thesis"))
    if not data.get("summary"):
        data["summary"] = clip_brief(data.get("core_thesis") or "")

    decision = str(data.get("decision") or "").strip().lower()
    if decision == "buy":
        decision = "proceed"
    data["decision"] = decision if decision in {"proceed", "watch", "avoid"} else "watch"

    raw_scores = data.get("dimension_scores") if isinstance(data.get("dimension_scores"), list) else data.get("six_dim_scores")
    scores = []
    for item in raw_scores if isinstance(raw_scores, list) else []:
        if not isinstance(item, dict):
            continue
        key = DIMENSION_ALIASES.get(str(item.get("dimension") or item.get("key") or "").strip())
        if key not in DIMENSION_KEYS:
            continue
        try:
            score = float(item.get("rating") if item.get("rating") is not None else item.get("score"))
        except (TypeError, ValueError):
            continue
        if not 1 <= score <= 5:
            continue
        scores.append(
            {
                "key": key,
                "score": round(score, 1),
                "gate": str(item.get("gate") or "").strip() or None,
                "confidence": _confidence_number(item.get("confidence")),
                "confidence_label": str(item.get("confidence") or "").strip() or None,
                "note": clip_brief(item.get("one_line") or item.get("note")),
            }
        )
    data["six_dim_scores"] = scores

    conflicts = []
    for item in data.get("conflicts") if isinstance(data.get("conflicts"), list) else []:
        if isinstance(item, dict):
            issue = str(item.get("issue") or "").strip()
            ruling = str(item.get("ruling") or "").strip()
            basis = str(item.get("basis") or "").strip()
            verify = str(item.get("verify_by") or "").strip()
            text = "：".join(x for x in (issue, ruling) if x)
            if basis:
                text = f"{text}（依据：{basis}" + (f"；验证：{verify}）" if verify else "）")
            elif verify:
                text = f"{text}（验证：{verify}）"
            if item.get("unresolved"):
                text = f"{text}【未解决分歧】"
            if text:
                conflicts.append(text)
        elif str(item).strip():
            conflicts.append(str(item))
    data["conflicts"] = conflicts

    key_variables = []
    raw_variables = data.get("key_variables")
    if isinstance(raw_variables, dict):
        raw_variables = [raw_variables]
    if not isinstance(raw_variables, list):
        raw_variables = []
    single = data.get("key_variable")
    if isinstance(single, dict):
        raw_variables = [single] + raw_variables
    for item in raw_variables:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            current = str(item.get("current") or "").strip()
            threshold = str(item.get("threshold") or "").strip()
            source = str(item.get("source") or "").strip()
            frequency = str(item.get("frequency") or "").strip()
            text = f"{name}：当前 {current or '待补'}，阈值 {threshold or '待定'}"
            if source:
                text += f"，来源 {source}"
            if frequency:
                text += f"，频率 {frequency}"
            if name:
                key_variables.append(text)
        elif str(item).strip():
            key_variables.append(str(item))
    data["key_variables"] = key_variables

    if not data.get("risks"):
        risks = []
        for item in data.get("pre_mortem") or []:
            if isinstance(item, dict):
                reason = str(item.get("reason") or "").strip()
                probability = item.get("probability")
                signal = str(item.get("early_signal") or "").strip()
                text = reason
                if probability not in (None, ""):
                    text += f"（概率 {probability}）"
                if signal:
                    text += f"；早期信号：{signal}"
                if text:
                    risks.append(text)
            elif str(item).strip():
                risks.append(str(item))
        data["risks"] = risks
    data["risks"] = [clip_brief(x) for x in data.get("risks") or [] if str(x).strip()]

    if not data.get("open_questions"):
        questions = []
        for item in data.get("unresolved") or []:
            if isinstance(item, dict):
                text = _text(item, "issue", "text", "detail")
            else:
                text = str(item).strip()
            if text:
                questions.append(text)
        data["open_questions"] = questions

    price_range = None
    band = data.get("price_band")
    if isinstance(band, (list, tuple)) and len(band) >= 2:
        try:
            low, high = float(band[0]), float(band[1])
        except (TypeError, ValueError):
            low = high = None
        if low is not None and high is not None:
            try:
                base = float(data.get("base_value"))
            except (TypeError, ValueError):
                base = None
            price_range = {"low": low, "base": base, "high": high, "note": "研究价格带，不是目标价"}
    if price_range is None and isinstance(data.get("price_range"), dict):
        raw_range = data["price_range"]
        price_range = {}
        for key in ("low", "base", "high"):
            try:
                price_range[key] = float(raw_range.get(key))
            except (TypeError, ValueError):
                price_range[key] = None
        price_range["note"] = clip_brief(raw_range.get("note") or "研究区间，不是目标价")
        if not any(price_range.get(k) is not None for k in ("low", "base", "high")):
            price_range = None
    data["price_range"] = price_range
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
        max_tokens=16000,
        timeout_sec=240,
        executors=("local",),
        validator=validate_debate,
    )
)

INDUSTRY_TASK = register(
    TaskSpec(
        task_id="inst.industry",
        description="机构端独立行业分析：空间、周期、产业链、竞争格局与政策",
        temperature=0.2,
        max_tokens=16000,
        timeout_sec=240,
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
        max_tokens=16000,
        timeout_sec=240,
        executors=("local",),
        validator=validate_research_memo,
    )
)

DIMENSION_CHAT_TASK = register(
    TaskSpec(
        task_id="inst.dim.chat",
        description="机构端单维对话：围绕一个研究维度与证据回答追问",
        temperature=0.3,
        max_tokens=4000,
        timeout_sec=120,
        executors=("local",),
        validator=validate_chat,
    )
)

RISK_REVIEW_TASK = register(
    TaskSpec(
        task_id="inst.risk_review",
        description="机构端独立风控复核意见（只建议，不改变状态）",
        temperature=0.2,
        max_tokens=8000,
        timeout_sec=180,
        executors=("local",),
        validator=validate_memo,
    )
)

CHAIRMAN_MEMO_TASK = register(
    TaskSpec(
        task_id="inst.chairman_memo",
        description="机构端 Chairman 一页式决策摘要（不含目标价与买卖指令）",
        temperature=0.2,
        max_tokens=8000,
        timeout_sec=180,
        executors=("local",),
        validator=validate_memo,
    )
)

FINANCIAL_ROLE_TASK = register(
    TaskSpec(
        task_id="inst.role.financial",
        description="机构端 AI 岗位：财务与取证（三表勾稽、ROIC/FCF、应收存货与会计风险）",
        temperature=0.2,
        max_tokens=12000,
        timeout_sec=240,
        executors=("local",),
        validator=validate_memo,
    )
)

GOVERNANCE_ROLE_TASK = register(
    TaskSpec(
        task_id="inst.role.governance",
        description="机构端 AI 岗位：治理/估值/反证（资本配置、DCF 假设、可检验反证条件）",
        temperature=0.2,
        max_tokens=12000,
        timeout_sec=240,
        executors=("local",),
        validator=validate_memo,
    )
)

POST_INVESTMENT_ROLE_TASK = register(
    TaskSpec(
        task_id="inst.role.post_investment",
        description="机构端 AI 岗位：投后/退出/复盘（论点台账、经营预警、退出备忘录与归因）",
        temperature=0.2,
        max_tokens=12000,
        timeout_sec=240,
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
            max_tokens=12000,
            timeout_sec=240,
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
