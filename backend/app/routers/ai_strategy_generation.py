# -*- coding: utf-8 -*-
"""AI 向量化策略生成端点（ADR-037 P1-3，自 ResearchEngine 迁入）。

契约与 RE `/api/ai/strategy-generations` 一致；不支持的策略类型返回 200 + rejected。
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from ai.errors import AiError, AiNotConfigured, AiTimeout
from ai.router import run_task
from ai.router.tasks.strategy_generation import (
    CATALOG_VERSION,
    PROMPT_VERSION,
    unsupported_prompt_errors,
)
from app.deps import require_user
from services.core.ai_strategy_input import strategy_prompt_error

router = APIRouter(tags=["ai"])

_IDEMPOTENCY: dict[str, tuple[str, dict[str, Any]]] = {}
_IDEMPOTENCY_LOCK = Lock()
_MAX_IDEMPOTENCY_ENTRIES = 512


def _http(exc: AiError) -> HTTPException:
    if isinstance(exc, AiNotConfigured):
        return HTTPException(status_code=503, detail="AI 策略生成服务尚未配置")
    if isinstance(exc, AiTimeout):
        return HTTPException(status_code=504, detail="AI 供应商请求超时")
    return HTTPException(status_code=502, detail=str(exc))


def _validate(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="请求体必须是 JSON 对象")
    error = strategy_prompt_error(body.get("prompt"))
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
    try:
        key = str(UUID(str(body.get("idempotency_key"))))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="idempotency_key 必须是 UUID") from exc
    return {
        "prompt": str(body["prompt"]),
        "context": {
            "universe": context.get("universe"),
            "frequency": frequency,
            "preferred_strategy_name": context.get("preferred_strategy_name"),
        },
        "idempotency_key": key,
    }


def _payload(
    *, strategy: dict[str, Any] | None, errors: list[str], model: str, latency_ms: int
) -> dict[str, Any]:
    return {
        "generation_id": f"sg_{uuid4().hex}",
        "status": "ready" if strategy is not None and not errors else "rejected",
        "strategy": strategy if not errors else None,
        "validation": {
            "status": "passed" if not errors else "failed",
            "capability_catalog_version": CATALOG_VERSION,
            "errors": list(errors),
            "warnings": [],
        },
        "meta": {"model_alias": model, "prompt_version": PROMPT_VERSION, "latency_ms": latency_ms},
    }


def _generate(req: dict[str, Any]) -> dict[str, Any]:
    # 能力预检先于模型调用：不支持的需求不花钱。
    unsupported = unsupported_prompt_errors(req["prompt"])
    if unsupported:
        return _payload(strategy=None, errors=unsupported, model="not_called", latency_ms=0)

    context = req["context"]
    variables = {
        "prompt": req["prompt"],
        "universe": context["universe"],
        "frequency": context["frequency"],
        "preferred_strategy_name": context["preferred_strategy_name"],
    }
    started = time.perf_counter()
    try:
        out = run_task("research.generate_strategy", variables=variables)
    except AiError as exc:
        raise _http(exc) from exc
    parsed = out.get("data") or {}
    return _payload(
        strategy=parsed.get("strategy"),
        errors=list(parsed.get("errors") or []),
        model=str(out.get("model") or ""),
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


@router.post("/api/ai/strategy-generations")
def ai_strategy_generations(body: dict[str, Any], _user: dict = Depends(require_user)) -> dict[str, Any]:
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
