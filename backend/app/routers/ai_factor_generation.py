# -*- coding: utf-8 -*-
"""AI 因子生成端点（ADR-037 P1-3，自 ResearchEngine 迁入）。

请求/响应契约与 RE `/api/ai/factor-generations` 一致：
- 只生成与静态校验，永不执行模型输出；
- 「需求不支持/需澄清」返回 200 + status=rejected；
- 代码不合规时自动修正一次，超时不丢首次校验信息。
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from ai.errors import AiError, AiNotConfigured, AiTimeout
from ai.router import run_task
from ai.router.specs import TaskRequest
from ai.router.tasks.factor_generation import (
    CATALOG_VERSION,
    PROMPT_VERSION,
    build_messages,
    is_request_rejection,
)
from app.deps import require_user
from services.core.ai_factor_input import factor_prompt_error

router = APIRouter(tags=["ai"])

_IDEMPOTENCY: dict[str, tuple[str, dict[str, Any]]] = {}
_IDEMPOTENCY_LOCK = Lock()
_MAX_IDEMPOTENCY_ENTRIES = 512

_REPAIR_HINT = (
    "草稿未通过平台静态校验：{errors}。请保持原需求的公式、周期和缺失值规则，"
    "仅修正不兼容语法，重新输出完整JSON。"
    "不要删除安全校验，不要改用替代数据；无法满足则返回unsupported及reason。"
)


def _http(exc: AiError) -> HTTPException:
    if isinstance(exc, AiNotConfigured):
        status = 503
    elif isinstance(exc, AiTimeout):
        status = 504
    else:
        status = 502
    detail = "AI 因子生成服务尚未配置" if isinstance(exc, AiNotConfigured) else str(exc)
    return HTTPException(status_code=status, detail=detail)


def _validate(body: object, *, max_prompt_chars: int = 2000) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="请求体必须是 JSON 对象")
    error = factor_prompt_error(body.get("prompt"), max_chars=max_prompt_chars)
    if error:
        raise HTTPException(status_code=422, detail=error)
    context = body.get("context", {})
    if context is None:
        context = {}
    if not isinstance(context, dict):
        raise HTTPException(status_code=422, detail="context 必须是 JSON 对象")
    frequency = context.get("frequency", "1d")
    if frequency not in ("1d",):
        raise HTTPException(status_code=422, detail="frequency 目前只支持 1d")
    libraries = context.get("allowed_library_names", [])
    if not isinstance(libraries, list) or any(not isinstance(item, str) for item in libraries):
        raise HTTPException(status_code=422, detail="allowed_library_names 必须是字符串数组")
    try:
        key = str(UUID(str(body.get("idempotency_key"))))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="idempotency_key 必须是 UUID") from exc
    custom=context.get("custom_source_contract")
    if custom is not None:
        from services.quant_factor.source_contract import VERSION
        if custom!=VERSION:raise HTTPException(422,"自定义源码契约版本未支持")
    return {
        "prompt": str(body["prompt"]),
        "context": {
            "universe": context.get("universe"),
            "frequency": frequency,
            "allowed_library_names": list(libraries),
            "preferred_factor_name": context.get("preferred_factor_name"),
            **({"custom_source_contract":custom} if custom else {}),
        },
        "idempotency_key": key,
    }


def _variables(req: dict[str, Any]) -> dict[str, Any]:
    context = req["context"]
    return {
        "prompt": req["prompt"],
        "universe": context["universe"],
        "frequency": context["frequency"],
        "allowed_library_names": context["allowed_library_names"],
        "preferred_factor_name": context["preferred_factor_name"],
    }


def _payload(parsed: dict[str, Any], model: str, latency_ms: int) -> dict[str, Any]:
    errors = list(parsed.get("errors") or [])
    factor = parsed.get("factor") if not errors else None
    return {
        "generation_id": f"fg_{uuid4().hex}",
        "status": "ready" if factor is not None and not errors else "rejected",
        "factor": factor,
        "validation": {
            "status": "passed" if not errors else "failed",
            "capability_catalog_version": CATALOG_VERSION,
            "errors": errors,
            "warnings": [],
            **({"source_contract":parsed["quant_source_contract"]} if parsed.get("quant_source_contract") else {}),
        },
        "meta": {"model_alias": model, "prompt_version": PROMPT_VERSION, "latency_ms": latency_ms},
    }


def _check_quant_source(parsed,req):
    if not req['context'].get('custom_source_contract'):return parsed
    parsed=dict(parsed)
    if parsed.get('errors'):return parsed
    factor=parsed.get('factor') or {}
    from services.quant_factor.source_contract import inspect_source
    try:parsed['quant_source_contract']=inspect_source(str(factor.get('factor_code') or ''),str(factor.get('factor_name') or ''))
    except ValueError as exc:parsed['errors']=[str(exc)]
    return parsed


def _generate(req: dict[str, Any]) -> dict[str, Any]:
    variables = _variables(req)
    started = time.perf_counter()
    try:
        first = run_task("research.generate_factor", variables=variables)
    except AiError as exc:
        raise _http(exc) from exc

    parsed = _check_quant_source(first.get("data") or {},req)
    model = str(first.get("model") or "")
    errors = list(parsed.get("errors") or [])

    # 仅对「可执行性」失败做一次受控修正；需求本身不支持时直接说明原因。
    if errors and not is_request_rejection(errors):
        repair = build_messages(TaskRequest(variables=variables)) + [
            {"role": "assistant", "content": str(first.get("content") or "")},
            {"role": "user", "content": _REPAIR_HINT.format(errors="；".join(errors))},
        ]
        try:
            second = run_task("research.generate_factor", messages=repair)
        except AiError:
            payload = _payload(parsed, model, round((time.perf_counter() - started) * 1000))
            payload["validation"]["warnings"].append("自动修正暂未完成，请稍后重试")
            return payload
        parsed = _check_quant_source(second.get("data") or parsed,req)
        model = str(second.get("model") or model)

    return _payload(parsed, model, round((time.perf_counter() - started) * 1000))


@router.post("/api/ai/factor-generations")
def ai_factor_generations(body: dict[str, Any], _user: dict = Depends(require_user)) -> dict[str, Any]:
    req = _validate(body)
    key = req["idempotency_key"]
    digest = f"{key}:{req['prompt']}:{req['context']}"
    with _IDEMPOTENCY_LOCK:
        existing = _IDEMPOTENCY.get(key)
        if existing is not None:
            if existing[0] != digest:
                raise HTTPException(status_code=409, detail="idempotency_key 已用于不同请求")
            return existing[1]

    response = _generate(req)
    with _IDEMPOTENCY_LOCK:
        if len(_IDEMPOTENCY) > _MAX_IDEMPOTENCY_ENTRIES:
            _IDEMPOTENCY.clear()
        existing = _IDEMPOTENCY.setdefault(key, (digest, response))
    if existing[0] != digest:
        raise HTTPException(status_code=409, detail="idempotency_key 已用于不同请求")
    return existing[1]


__all__ = ["router"]
