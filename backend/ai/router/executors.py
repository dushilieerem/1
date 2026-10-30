# -*- coding: utf-8 -*-
"""执行链成员（ADR-037 §3）。

`local` 走供应商层；`re` 走研究计算服务。降级只在 `AiNotConfigured` 时发生：
上游故障不会被下一个执行者悄悄接管，否则排查成本高于收益。
"""
from __future__ import annotations

import json
from typing import Any, Callable

from ai.errors import (
    AiInvalidRequest,
    AiNotConfigured,
    AiTimeout,
    AiUpstreamError,
)
from ai.gateway import providers
from ai.router.specs import EXECUTOR_LOCAL, EXECUTOR_RE, TaskRequest, TaskSpec


def run_local(spec: TaskSpec, request: TaskRequest) -> dict[str, Any]:
    target = providers.resolve_target(slot=spec.slot, model=request.model)
    tools = request.tools if spec.allow_tools else None
    result = providers.complete(
        target,
        messages=list(request.messages),
        temperature=spec.temperature if request.temperature is None else request.temperature,
        max_tokens=spec.max_tokens,
        tools=tools,
        tool_choice=request.tool_choice if tools else None,
        response_format=spec.response_format,
        timeout=spec.timeout_sec,
    )
    return result


def run_re(spec: TaskSpec, request: TaskRequest) -> dict[str, Any]:
    from services.core.env_config import env

    if not (env("YG_RE_BASE", "") or "").strip():
        raise AiNotConfigured("未配置 YG_RE_BASE，无法调用研究计算服务")

    from services.core.re_http_gateway import forward_re

    payload = spec.re_payload(request) if spec.re_payload else dict(request.variables)
    status, _headers, data = forward_re(
        "POST",
        spec.re_path or "",
        payload=payload,
        timeout=int(spec.timeout_sec or 600),
    )
    if status == 404:
        # 端点未部署视为“该执行者不可用”，允许链上后续成员接手。
        raise AiNotConfigured(f"研究计算服务未提供 {spec.re_path}")
    if status in (401, 403):
        raise AiNotConfigured("研究计算服务拒绝访问，请检查服务端凭据")
    if status == 429:
        raise AiUpstreamError("研究计算服务限流（HTTP 429）")
    if status >= 500:
        raise AiUpstreamError(f"研究计算服务 HTTP {status}")
    if status >= 400:
        detail = data.get("detail") if isinstance(data, dict) else None
        raise AiInvalidRequest(str(detail or f"研究计算服务 HTTP {status}"))
    if not isinstance(data, dict):
        raise AiUpstreamError("研究计算服务返回非 JSON 对象")
    if spec.re_parse is not None:
        return spec.re_parse(data)
    return {
        "content": json.dumps(data, ensure_ascii=False),
        "message": {},
        "tool_calls": [],
        "tokens_in": int(data.get("tokens_in") or 0),
        "tokens_out": int(data.get("tokens_out") or 0),
        "model": str(data.get("model") or ""),
        "provider": "research_engine",
    }


EXECUTORS: dict[str, Callable[[TaskSpec, TaskRequest], dict[str, Any]]] = {
    EXECUTOR_LOCAL: run_local,
    EXECUTOR_RE: run_re,
}


def can_run(spec: TaskSpec) -> bool:
    """该任务的执行链首成员当前是否可用（用于 feature 层决定是否走 mock）。"""
    first = spec.executors[0]
    if first == EXECUTOR_LOCAL:
        return providers.is_configured(spec.slot)
    if first == EXECUTOR_RE:
        from services.core.env_config import env

        return bool((env("YG_RE_BASE", "") or "").strip())
    return False


__all__ = ["EXECUTORS", "can_run", "run_local", "run_re"]
