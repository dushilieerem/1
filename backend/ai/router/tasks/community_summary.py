# -*- coding: utf-8 -*-
"""社区读帖摘要的响应契约与 RE 回退映射（ADR-037 P1-1）。

prompt 仍由社区侧持有（依赖 platform_ref / 数据可信度领域知识，
不适合下沉到路由层）；本模块负责：
- 模型输出必须是含非空 `summary_md` 的 JSON（`response_format` + `validator`）；
- 本地不可用时按既有口径转发研究计算服务，并把其响应映射成统一结果。
"""
from __future__ import annotations

import json
from typing import Any

from ai.errors import AiBadOutput
from ai.router.specs import (
    EXECUTOR_LOCAL,
    EXECUTOR_RE,
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


def re_payload(request: TaskRequest) -> dict[str, Any]:
    """研究计算服务仍按 PostSummaryRequest 接收；字段与本地 variables 同源。"""
    variables = request.variables
    return {
        "title": str(variables.get("title") or "")[:512],
        "body": str(variables.get("body") or "")[:20000],
        "code_snippet": str(variables.get("code_snippet") or "")[:20000],
        "grounding": variables.get("grounding") or {},
        "truncated": bool(variables.get("truncated")),
    }


def parse_re_summary(data: dict[str, Any]) -> dict[str, Any]:
    """把研究计算服务的响应映射成统一结果；非模型结果一律视为失败。"""
    if str(data.get("summary_source") or "") != "llm":
        raise AiBadOutput("共享AI摘要服务返回来源无效，未生成AI摘要")
    summary = data.get("summary_md")
    if not isinstance(summary, str) or not summary.strip():
        raise AiBadOutput("共享AI摘要服务返回空摘要")
    return {
        "content": summary.strip(),
        "model": str(data.get("model") or ""),
        "provider": "research_engine",
        "tokens_in": int(data.get("tokens_in") or 0),
        "tokens_out": int(data.get("tokens_out") or 0),
        "data": {"summary_md": summary.strip()},
    }


SUMMARY_TASK = register(
    TaskSpec(
        task_id="community.summarize_post",
        description="读帖摘要（TL;DR）；本地优先，研究计算服务兜底",
        temperature=0.2,
        max_tokens=450,
        timeout_sec=60,
        response_format=SUMMARY_SCHEMA,
        executors=(EXECUTOR_LOCAL, EXECUTOR_RE),
        validator=validate_summary,
        re_path="/api/ai/post-summaries",
        re_payload=re_payload,
        re_parse=parse_re_summary,
    )
)

__all__ = [
    "PROMPT_VERSION",
    "SUMMARY_SCHEMA",
    "SUMMARY_TASK",
    "parse_re_summary",
    "re_payload",
    "validate_summary",
]
