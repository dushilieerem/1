# -*- coding: utf-8 -*-
"""回测解读端点：本地确定性证据 + 可选模型排序（ADR-037 P1-2）。

请求/响应契约与 ResearchEngine `/api/ai/backtest-interpretations` 保持一致，
鉴权、幂等与错误语义改由本仓提供；模型调用经 `ai.router`。
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException

from ai.errors import AiError
from ai.router import available_task, run_task
from app.deps import require_user
from services.core.env_config import env
from services.research import backtest_evidence as evidence_mod

router = APIRouter(tags=["ai"])

_MAX_IDEMPOTENCY_ENTRIES = 512
_IDEMPOTENCY: dict[str, tuple[str, dict[str, Any]]] = {}
_IDEMPOTENCY_LOCK = Lock()

_BACKTEST_TYPES = {"factor", "strategy"}
_FOCUS = {"overall", "risk", "robustness", "factor", "execution"}


def _bad_request(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _validate(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise _bad_request(422, "请求体必须是 JSON 对象")
    backtest_type = body.get("backtest_type")
    if backtest_type not in _BACKTEST_TYPES:
        raise _bad_request(422, "backtest_type 必须是 factor 或 strategy")
    result = body.get("result")
    if not isinstance(result, dict):
        raise _bad_request(422, "result 必须是 JSON 对象")
    run_context = body.get("run_context", {})
    if run_context is None:
        run_context = {}
    if not isinstance(run_context, dict):
        raise _bad_request(422, "run_context 必须是 JSON 对象")
    focus = body.get("focus", "overall")
    if focus not in _FOCUS:
        raise _bad_request(422, "focus 取值不合法")
    question = body.get("question")
    if question is not None:
        if not isinstance(question, str) or not (1 <= len(question) <= 500):
            raise _bad_request(422, "question 长度必须在 1..500")
    raw_key = body.get("idempotency_key")
    try:
        key = str(UUID(str(raw_key)))
    except (TypeError, ValueError) as exc:
        raise _bad_request(422, "idempotency_key 必须是 UUID") from exc
    return {
        "backtest_type": backtest_type,
        "result": result,
        "run_context": run_context,
        "focus": focus,
        "question": question,
        "idempotency_key": key,
    }


def _meta(model_alias: str, started: float) -> dict[str, Any]:
    return {
        "model_alias": model_alias,
        "prompt_version": evidence_mod.PROMPT_VERSION,
        "diagnostic_catalog_version": evidence_mod.DIAGNOSTIC_CATALOG_VERSION,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


def _terminal(status: str, summary: str, started: float) -> dict[str, Any]:
    interpretation = None
    if status != "rejected":
        interpretation = {"summary": summary, "findings": [], "experiments": []}
    return {
        "interpretation_id": f"bi_{uuid4().hex}",
        "status": status,
        "mode": "not_applicable",
        "evidence": {
            "schema_version": evidence_mod.EVIDENCE_SCHEMA_VERSION,
            "result_fingerprint": "sha256:unavailable",
            "coverage": "insufficient",
            "warnings": [status.upper()],
            "items": [],
        },
        "interpretation": interpretation,
        "disclaimer": evidence_mod.DISCLAIMER,
        "meta": _meta("not_called", started),
    }


def _build_response(req: dict[str, Any], started: float) -> dict[str, Any]:
    result = req["result"]
    if result.get("error"):
        return _terminal("rejected", "提交的回测结果包含业务错误，无法进行解读。", started)

    points = evidence_mod.valid_points(result.get("equity_curve"))
    if points is None:
        raise _bad_request(422, "equity_curve 必须是日期递增、值为有限数值的序列")
    if len(points) > evidence_mod.MAX_CURVE_POINTS:
        raise _bad_request(400, "单条净值曲线最多 10,000 点")
    if len(points) < evidence_mod.MIN_CURVE_POINTS:
        return _terminal("insufficient", "有效净值点少于 60，建议补齐数据后再解读。", started)

    evidence, codes = evidence_mod.build_evidence(
        backtest_type=req["backtest_type"],
        result=result,
        run_context=req["run_context"],
        points=points,
    )
    items = evidence_mod.findings(codes)
    interpretation: dict[str, Any] = {
        "summary": evidence_mod.summary(codes),
        "findings": items,
        "experiments": evidence_mod.experiments(items),
    }
    mode = "deterministic_fallback"
    model_alias = "not_configured"

    # 模型只参与排序；请求中只有候选 ID（无数值、无原始快照）。
    if items and available_task("research.interpret_backtest"):
        try:
            out = run_task(
                "research.interpret_backtest",
                variables={
                    "focus": req["focus"],
                    "question": req["question"],
                    "candidates": [{"id": i["candidate_id"], "title": i["title"]} for i in items],
                },
            )
            ordered = evidence_mod.order_findings(items, (out.get("data") or {}).get("finding_ids") or [])
            interpretation = {
                "summary": interpretation["summary"],
                "findings": ordered,
                "experiments": evidence_mod.experiments(ordered),
            }
            mode = "llm_grounded"
            model_alias = str(out.get("model") or "")
        except AiError:
            # 排序失败不影响确定性报告：与 RE 的降级语义一致。
            pass

    return {
        "interpretation_id": f"bi_{uuid4().hex}",
        "status": "ready",
        "mode": mode,
        "evidence": evidence,
        "interpretation": interpretation,
        "disclaimer": evidence_mod.DISCLAIMER,
        "meta": _meta(model_alias, started),
    }


@router.post("/api/ai/backtest-interpretations")
def ai_backtest_interpretations(
    body: dict[str, Any], _user: dict = Depends(require_user)
) -> dict[str, Any]:
    if (env("AI_BACKTEST_INTERPRETATION_ENABLED", "true") or "true").lower() == "false":
        raise _bad_request(503, "AI 回测解读服务已关闭")

    req = _validate(body)
    key = req["idempotency_key"]
    digest = evidence_mod.request_hash(body)
    with _IDEMPOTENCY_LOCK:
        existing = _IDEMPOTENCY.get(key)
        if existing is not None:
            if existing[0] != digest:
                raise _bad_request(409, "idempotency_key 已用于不同请求")
            return existing[1]

    started = time.perf_counter()
    response = _build_response(req, started)
    with _IDEMPOTENCY_LOCK:
        if len(_IDEMPOTENCY) > _MAX_IDEMPOTENCY_ENTRIES:
            _IDEMPOTENCY.clear()
        existing = _IDEMPOTENCY.setdefault(key, (digest, response))
    if existing[0] != digest:
        raise _bad_request(409, "idempotency_key 已用于不同请求")
    return existing[1]
