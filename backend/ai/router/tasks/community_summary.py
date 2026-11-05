# -*- coding: utf-8 -*-
"""社区读帖摘要的响应契约（ADR-037 P1-1）。

prompt 仍由社区侧持有（依赖 platform_ref / 数据可信度领域知识，
不适合下沉到路由层）；本模块负责：
- 模型输出必须是含非空 `summary_md` 的 JSON（`response_format` + `validator`）；
- 社区摘要已完全移交 SVQuant，只走本地 LLM 网关，不再回退研究计算服务。
"""
from __future__ import annotations

import json
from typing import Any

from ai.errors import AiBadOutput
from ai.router.specs import (
    EXECUTOR_LOCAL,
    TaskRequest,
    TaskSpec,
    register,
)

PROMPT_VERSION = "post-summary-v1"

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "svquant_post_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary_md"],
            "properties": {"summary_md": {"type": "string"}},
        },
    },
}


def _strip_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


def validate_summary(raw: str, request: TaskRequest) -> dict[str, Any]:
    """校验模型输出：必须是含非空 summary_md 的 JSON 对象。"""
    _ = request
    try:
        data = json.loads(_strip_fence(raw))
    except (json.JSONDecodeError, IndexError, ValueError) as exc:
        raise AiBadOutput("AI模型没有返回有效摘要，请稍后重试") from exc
    summary = data.get("summary_md") if isinstance(data, dict) else None
    if not isinstance(summary, str) or not summary.strip():
        raise AiBadOutput("AI模型没有返回有效摘要，请稍后重试")
    return {"summary_md": summary.strip()}


SUMMARY_TASK = register(
    TaskSpec(
        task_id="community.summarize_post",
        description="读帖摘要（TL;DR）；仅走本地 LLM 网关",
        temperature=0.2,
        max_tokens=450,
        timeout_sec=60,
        response_format=SUMMARY_SCHEMA,
        executors=(EXECUTOR_LOCAL,),
        validator=validate_summary,
    )
)

__all__ = [
    "PROMPT_VERSION",
    "SUMMARY_SCHEMA",
    "SUMMARY_TASK",
    "validate_summary",
]
