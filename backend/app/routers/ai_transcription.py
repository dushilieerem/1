# -*- coding: utf-8 -*-
"""AI 策略转写端点（聚宽 → SVQuant，ADR-037 P1-4，自 ResearchEngine 迁入）。

契约与 RE `/api/ai/strategy-transcriptions` 一致：同步执行，能力核对先于模型调用；
阻断项未确认时返回 200 + needs_input，report_only 返回 200 + 不生成代码。
"""
from __future__ import annotations

import hashlib
import json
import time
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from ai.errors import AiError, AiNotConfigured, AiTimeout
from ai.router import run_task
from ai.router.tasks.strategy_transcription import CATALOG_VERSION, PROMPT_VERSION
from app.deps import require_user
from services.core.strategy_transcription_input import strategy_transcription_error
from services.strategy.transcription_validation import (
    MAX_LLM_SOURCE_CHARS,
    MAX_SOURCE_CHARS,
    capability_issues,
    data_version,
    detect_engine,
    generated_error_issue,
    make_check,
    parse_inventory,
    requires_ack,
    resolve_issues,
    skipped_checks,
    summary,
    transcription_mappings,
    verdict,
)

router = APIRouter(tags=["ai"])

_IDEMPOTENCY: dict[str, tuple[str, dict[str, Any]]] = {}
_IDEMPOTENCY_LOCK = Lock()
_MAX_IDEMPOTENCY_ENTRIES = 512

_ALLOWED_BODY = {"code", "context", "idempotency_key"}
_ALLOWED_CONTEXT = {"target", "accepted_degradations", "report_only", "source_name"}
_ALLOWED_TARGET = {"engine_mode", "universe", "benchmark", "start", "end", "initial_capital"}
_ENGINE_MODES = {"auto", "vectorized", "event"}


def _http(exc: AiError) -> HTTPException:
    if isinstance(exc, AiNotConfigured):
        return HTTPException(status_code=503, detail="AI 策略转写服务尚未配置")
    if isinstance(exc, AiTimeout):
        return HTTPException(status_code=504, detail="AI 供应商请求超时")
    return HTTPException(status_code=502, detail=str(exc))


def _reject_unknown(payload: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(payload) - allowed
    if extra:
        raise HTTPException(
            status_code=422, detail=f"{label}不支持的字段：{', '.join(sorted(extra))}"
        )


def _validate(body: object) -> dict[str, Any]:
    error = strategy_transcription_error(body)
    if error:
        raise HTTPException(status_code=422, detail=error)
    assert isinstance(body, dict)
    _reject_unknown(body, _ALLOWED_BODY, "请求体")

    context = body.get("context") or {}
    _reject_unknown(context, _ALLOWED_CONTEXT, "context ")

    target = context.get("target")
    if target is None:
        target = {}
    if not isinstance(target, dict):
        raise HTTPException(status_code=422, detail="target 必须是 JSON 对象")
    _reject_unknown(target, _ALLOWED_TARGET, "target ")

    engine_mode = target.get("engine_mode", "auto")
    if engine_mode not in _ENGINE_MODES:
        raise HTTPException(status_code=422, detail="engine_mode 必须是 auto/vectorized/event")
    for name in ("universe", "benchmark", "start", "end"):
        value = target.get(name)
        if value is not None and not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"{name} 必须是字符串")
    capital = target.get("initial_capital")
    if capital is not None and (
        isinstance(capital, bool)
        or not isinstance(capital, (int, float))
        or capital <= 0
    ):
        raise HTTPException(status_code=422, detail="initial_capital 必须大于 0")

    source_name = context.get("source_name")
    if source_name is not None and not isinstance(source_name, str):
        raise HTTPException(status_code=422, detail="source_name 必须是字符串")

    try:
        key = str(UUID(str(body.get("idempotency_key"))))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="idempotency_key 必须是 UUID") from exc

    return {
        "code": str(body["code"]),
        "context": {
            "target": {
                "engine_mode": engine_mode,
                "universe": target.get("universe"),
                "benchmark": target.get("benchmark"),
                "start": target.get("start"),
                "end": target.get("end"),
                "initial_capital": float(capital) if capital is not None else None,
            },
            "accepted_degradations": list(context.get("accepted_degradations") or []),
            "report_only": bool(context.get("report_only", False)),
            "source_name": source_name,
        },
        "idempotency_key": key,
    }


def _request_hash(req: dict[str, Any]) -> str:
    content = json.dumps(
        {"code": req["code"], "context": req["context"]},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(content.encode()).hexdigest()


def _meta(model: str, latency_ms: int) -> dict[str, Any]:
    return {
        "model_alias": model,
        "prompt_version": PROMPT_VERSION,
        "capability_catalog_version": CATALOG_VERSION,
        "data_version": data_version(),
        "latency_ms": latency_ms,
    }


def _base_response(
    *, transcription_id: str, status: str, verdict: str, target_engine: str,
    runnable: bool, requires_ack_value: bool, summary_text: str,
    issues: list[dict[str, Any]], mappings: list[dict[str, Any]],
    assumptions: list[str], checks: list[dict[str, Any]],
    errors: list[str], strategy: dict[str, Any] | None,
    model: str, latency_ms: int,
) -> dict[str, Any]:
    return {
        "transcription_id": transcription_id,
        "status": status,
        "verdict": verdict,
        "target_engine": target_engine,
        "runnable": runnable,
        "requires_ack": requires_ack_value,
        "summary": summary_text,
        "issues": issues,
        "mappings": mappings,
        "assumptions": assumptions,
        "checks": checks,
        "errors": errors,
        "strategy": strategy,
        "meta": _meta(model, latency_ms),
    }


def _rejected_response(
    *, target_engine: str, errors: list[str],
    checks: list[dict[str, Any]] | None = None,
    issues: list[dict[str, Any]] | None = None,
    mappings: list[dict[str, Any]] | None = None,
    assumptions: list[str] | None = None,
    latency_ms: int = 0,
    model: str = "not_called",
) -> dict[str, Any]:
    return _base_response(
        transcription_id=f"st_{uuid4().hex}",
        status="rejected",
        verdict="blocked",
        target_engine=target_engine,
        runnable=False,
        requires_ack_value=False,
        summary_text=errors[0] if errors else "转写失败。",
        issues=issues or [],
        mappings=mappings or [],
        assumptions=assumptions or [],
        checks=checks or [],
        errors=list(errors),
        strategy=None,
        model=model,
        latency_ms=latency_ms,
    )


def _needs_input_response(
    *, target_engine: str, issues: list[dict[str, Any]],
    mappings: list[dict[str, Any]], assumptions: list[str], latency_ms: int,
) -> dict[str, Any]:
    blockers = sum(1 for item in issues if item["severity"] == "blocker")
    return _base_response(
        transcription_id=f"st_{uuid4().hex}",
        status="needs_input",
        verdict="blocked",
        target_engine=target_engine,
        runnable=False,
        requires_ack_value=True,
        summary_text=f"存在 {blockers} 个阻断项：请选择降级方案，或仅导出报告。",
        issues=issues,
        mappings=mappings,
        assumptions=assumptions,
        checks=[],
        errors=[],
        strategy=None,
        model="not_called",
        latency_ms=latency_ms,
    )


def _report_only_response(
    *, target_engine: str, verdict_value: str, issues: list[dict[str, Any]],
    mappings: list[dict[str, Any]], assumptions: list[str], latency_ms: int,
) -> dict[str, Any]:
    return _base_response(
        transcription_id=f"st_{uuid4().hex}",
        status="report_only",
        verdict=verdict_value,
        target_engine=target_engine,
        runnable=False,
        requires_ack_value=False,
        summary_text=summary(verdict_value, issues),
        issues=issues,
        mappings=mappings,
        assumptions=assumptions,
        checks=[],
        errors=[],
        strategy=None,
        model="not_called",
        latency_ms=latency_ms,
    )


def _transcribe(req: dict[str, Any]) -> dict[str, Any]:
    context = req["context"]
    accepted = set(context["accepted_degradations"])
    source = req["code"].strip()
    target_engine = detect_engine(source, context["target"]["engine_mode"])
    started_at = time.perf_counter()

    if not source:
        return _rejected_response(
            target_engine=target_engine,
            errors=["代码为空，请粘贴完整的聚宽策略。"],
            checks=[
                make_check("syntax", "语法编译", "fail", "代码为空"),
                *skipped_checks("syntax"),
            ],
            latency_ms=0,
        )

    if len(source) > MAX_SOURCE_CHARS:
        return _rejected_response(
            target_engine=target_engine,
            errors=[f"代码超过 {MAX_SOURCE_CHARS} 字符上限，请拆分后再转写。"],
            checks=[
                make_check("syntax", "语法编译", "fail", "超过大小上限"),
                *skipped_checks("syntax"),
            ],
            latency_ms=0,
        )

    try:
        inventory = parse_inventory(source)
    except SyntaxError as exc:
        return _rejected_response(
            target_engine=target_engine,
            errors=[f"代码语法错误：第 {exc.lineno} 行，{exc.msg}。"],
            checks=[
                make_check(
                    "syntax", "语法编译", "fail",
                    f"第 {exc.lineno} 行：{exc.msg}", exc.lineno,
                ),
                *skipped_checks("syntax"),
            ],
            latency_ms=round((time.perf_counter() - started_at) * 1000),
        )

    issues = capability_issues(source, inventory)
    mappings = transcription_mappings(source, inventory)
    issues, accepted_notes, has_unresolved_blocker = resolve_issues(issues, accepted)
    assumptions = list(accepted_notes)

    force_report = context["report_only"] or "report_only" in accepted
    report_verdict = verdict(issues)
    if force_report:
        return _report_only_response(
            target_engine=target_engine,
            verdict_value=report_verdict,
            issues=issues,
            mappings=mappings,
            assumptions=assumptions,
            latency_ms=round((time.perf_counter() - started_at) * 1000),
        )

    if has_unresolved_blocker:
        return _needs_input_response(
            target_engine=target_engine,
            issues=issues,
            mappings=mappings,
            assumptions=assumptions,
            latency_ms=round((time.perf_counter() - started_at) * 1000),
        )

    if len(source) > MAX_LLM_SOURCE_CHARS:
        return _rejected_response(
            target_engine=target_engine,
            errors=[
                f"代码超过 {MAX_LLM_SOURCE_CHARS} 字符的模型输入上限，请按策略/函数拆分后再转写。"
            ],
            checks=[make_check("syntax", "语法编译", "fail", "代码过长，未调用模型")],
            issues=issues,
            mappings=mappings,
            latency_ms=round((time.perf_counter() - started_at) * 1000),
        )

    variables = {
        "code": req["code"],
        "context": context,
        "target_engine": target_engine,
        "issues": issues,
        "mappings": mappings,
    }
    try:
        out = run_task("research.transcribe_strategy", variables=variables)
    except AiError as exc:
        raise _http(exc) from exc

    parsed = out.get("data") or {}
    model = str(out.get("model") or "")
    latency_ms = round((time.perf_counter() - started_at) * 1000)

    if parsed.get("errors"):
        errors = list(parsed.get("errors") or [])
        return _rejected_response(
            target_engine=target_engine,
            errors=errors,
            checks=list(parsed.get("checks") or []),
            issues=[*issues, generated_error_issue(errors)],
            mappings=mappings,
            assumptions=assumptions,
            latency_ms=latency_ms,
            model=model,
        )

    final_verdict = verdict(issues)
    return _base_response(
        transcription_id=f"st_{uuid4().hex}",
        status="ready",
        verdict=final_verdict,
        target_engine=target_engine,
        runnable=True,
        requires_ack_value=requires_ack(issues),
        summary_text=summary(final_verdict, issues),
        issues=issues,
        mappings=mappings,
        assumptions=assumptions,
        checks=list(parsed.get("checks") or []),
        errors=[],
        strategy=parsed.get("strategy"),
        model=model,
        latency_ms=latency_ms,
    )


@router.post("/api/ai/strategy-transcriptions")
def ai_strategy_transcriptions(
    body: dict[str, Any], _user: dict = Depends(require_user)
) -> dict[str, Any]:
    req = _validate(body)
    key = req["idempotency_key"]
    digest = _request_hash(req)
    with _IDEMPOTENCY_LOCK:
        existing = _IDEMPOTENCY.get(key)
        if existing is not None:
            if existing[0] != digest:
                raise HTTPException(status_code=409, detail="idempotency_key 已用于不同请求")
            return existing[1]

    response = _transcribe(req)
    with _IDEMPOTENCY_LOCK:
        if len(_IDEMPOTENCY) > _MAX_IDEMPOTENCY_ENTRIES:
            _IDEMPOTENCY.clear()
        existing = _IDEMPOTENCY.setdefault(key, (digest, response))
    if existing[0] != digest:
        raise HTTPException(status_code=409, detail="idempotency_key 已用于不同请求")
    return existing[1]


__all__ = ["router"]
