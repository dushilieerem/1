# -*- coding: utf-8 -*-
"""回测解读：模型只给候选排序（prompt/校验器自 ResearchEngine 迁入，ADR-037 P1-2）。

数值永不发送给模型：请求里只有候选 id 与标题，模型输出必须是这些 id 的一个排列。
"""
from __future__ import annotations

import json
from typing import Any

from ai.errors import AiBadOutput
from ai.router.specs import TaskRequest, TaskSpec, register

PROMPT_VERSION = "v1"

ORDER_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "svquant_backtest_finding_order",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["finding_ids"],
            "properties": {"finding_ids": {"type": "array", "items": {"type": "string"}}},
        },
    },
}

SYSTEM_PROMPT = "只输出 JSON：{\"finding_ids\":[...] }。只能排列提供的 ID，不得生成数值、投资建议或新事实。"


def build_messages(request: TaskRequest) -> list[dict[str, Any]]:
    variables = request.variables
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "focus": variables.get("focus"),
                    "question": variables.get("question"),
                    "candidates": variables.get("candidates") or [],
                },
                ensure_ascii=False,
            ),
        },
    ]


def validate_order(raw: str, request: TaskRequest) -> dict[str, Any]:
    """输出必须是候选 id 的完整排列：不允许多、不允许少、不允许新 id。"""
    candidates = [str(item.get("id")) for item in (request.variables.get("candidates") or [])]
    valid = set(candidates)
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, IndexError, ValueError) as exc:
        raise AiBadOutput("模型未返回可用的排序结果") from exc
    ids = data.get("finding_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list) or set(ids) != valid or len(ids) != len(valid):
        raise AiBadOutput("模型返回的排序与候选集合不一致")
    return {"finding_ids": [str(i) for i in ids]}


INTERPRET_TASK = register(
    TaskSpec(
        task_id="research.interpret_backtest",
        description="回测解读诊断排序（只排序，不生成数值）",
        temperature=0.1,
        max_tokens=None,
        timeout_sec=60,
        response_format=ORDER_SCHEMA,
        prompt=build_messages,
        validator=validate_order,
    )
)

__all__ = ["INTERPRET_TASK", "ORDER_SCHEMA", "PROMPT_VERSION", "SYSTEM_PROMPT", "build_messages", "validate_order"]
