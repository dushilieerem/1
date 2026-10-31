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

PROMPT_VERSION = "inst-v1"


def _strip(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


def _load(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(_strip(raw))
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


def validate_memo(raw: str, request: TaskRequest) -> dict[str, Any]:
    data = _load(raw)
    for key in ("summary", "evidence", "risks", "open_questions"):
        value = data.get(key)
        if value is None:
            data[key] = [] if key != "summary" else ""
    return data


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

RESEARCH_MEMO_TASK = register(
    TaskSpec(
        task_id="inst.research_memo",
        description="机构端研究一页纸：结论、证据、反证、待核验",
        temperature=0.3,
        max_tokens=3000,
        timeout_sec=120,
        executors=("local",),
        validator=validate_memo,
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

__all__ = [
    "CHAIRMAN_MEMO_TASK",
    "DEBATE_TASK",
    "PROMPT_VERSION",
    "RESEARCH_MEMO_TASK",
    "RISK_REVIEW_TASK",
    "validate_debate",
    "validate_memo",
]
