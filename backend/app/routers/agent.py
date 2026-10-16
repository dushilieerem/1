# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_user
from ai.gateway.llm_client import LlmError
from ai.crews.strategy_research import run_backtest, run_backtest_chat
from ai.runtime import store as agent_store
from ai.runtime.runtime import start_run
from ai.runtime.store import (
    set_user_ai_quota,
    usage_admin_summary,
    usage_summary_for_user,
)
from ai.crews.gather_idea import (
    run_backtest_pipeline,
    run_eval_pipeline,
    run_factor_pipeline,
    run_gather_pipeline,
    run_idea_pipeline,
)

router = APIRouter(tags=["agent"])


def _perm_http(exc: PermissionError) -> HTTPException:
    msg = str(exc)
    return HTTPException(status_code=403 if "配额" in msg else 401, detail=msg)


@router.get("/api/agent/usage/me")
def agent_usage_me(
    user: dict = Depends(require_user),
    days: int = Query(7),
) -> dict:
    try:
        return usage_summary_for_user(int(user["id"]), days=days)
    except PermissionError as exc:
        raise _perm_http(exc) from exc


@router.get("/api/agent/usage")
def agent_usage_admin(
    user: dict = Depends(require_user),
    days: int = Query(7),
) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可查看")
    try:
        return usage_admin_summary(days=days)
    except PermissionError as exc:
        raise _perm_http(exc) from exc


@router.post("/api/agent/usage/quota")
def agent_set_quota(
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    try:
        return set_user_ai_quota(
            author_role=str(user.get("role") or "user"),
            user_id=int(body.get("user_id") or 0),
            quota_daily=int(body.get("quota_daily")),
        )
    except PermissionError as exc:
        raise _perm_http(exc) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="用户不存在") from None
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "参数无效") from exc


@router.post("/api/agent/runs")
def agent_runs(
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    skills = body.get("skills")
    if skills is not None and not isinstance(skills, list):
        raise HTTPException(status_code=400, detail="skills 须为数组")
    context = body.get("context")
    if context is not None and not isinstance(context, dict):
        raise HTTPException(status_code=400, detail="context 须为对象")
    try:
        return start_run(
            user_id=int(user["id"]),
            goal=str(body.get("goal") or ""),
            skills=[str(s) for s in skills] if skills else None,
            context=context or {},
            mode=str(body.get("mode") or "single"),
            crew=str(body.get("crew") or "") or None,
        )
    except PermissionError as exc:
        raise _perm_http(exc) from exc
    except (ValueError, LlmError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_pipeline(fn, body: dict[str, Any], user: dict) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body 须为 JSON 对象")
    try:
        return fn(body, user_id=int(user["id"]))
    except PermissionError as exc:
        raise _perm_http(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/agent/gather")
def agent_gather(body: dict[str, Any], user: dict = Depends(require_user)) -> dict:
    return _run_pipeline(run_gather_pipeline, body, user)


@router.post("/api/agent/idea")
def agent_idea(body: dict[str, Any], user: dict = Depends(require_user)) -> dict:
    return _run_pipeline(run_idea_pipeline, body, user)


@router.post("/api/agent/factor")
def agent_factor(body: dict[str, Any], user: dict = Depends(require_user)) -> dict:
    return _run_pipeline(run_factor_pipeline, body, user)


@router.post("/api/agent/factor-backtest")
def agent_factor_backtest(
    body: dict[str, Any], user: dict = Depends(require_user)
) -> dict:
    return _run_pipeline(run_backtest_pipeline, body, user)


@router.post("/api/agent/factor-eval")
def agent_factor_eval(
    body: dict[str, Any], user: dict = Depends(require_user)
) -> dict:
    return _run_pipeline(run_eval_pipeline, body, user)


# —— 策略研究 crew：真实回测工具（经 ResearchEngine 网关执行）——


@router.post("/api/agent/strategy-research/backtest")
def agent_strategy_research_backtest(
    body: dict[str, Any], user: dict = Depends(require_user)
) -> dict:
    """结构化直调 run_backtest 工具（不经 LLM），参数由 Pydantic 校验。"""
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body 须为 JSON 对象")
    try:
        agent_store.assert_quota_available(int(user["id"]), need=1)
        result = run_backtest(body, user_id=int(user["id"]))
        agent_store.record_usage(
            user_id=int(user["id"]),
            run_id=agent_store.new_run_id(),
            skill="run_backtest",
        )
        return result
    except PermissionError as exc:
        raise _perm_http(exc) from exc


@router.post("/api/agent/strategy-research/chat")
def agent_strategy_research_chat(
    body: dict[str, Any], user: dict = Depends(require_user)
) -> dict:
    """自然语言 → 模型 Tool Calling → run_backtest → 基于真实结果作答。"""
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body 须为 JSON 对象")
    message = str(body.get("message") or "")
    history = body.get("history")
    if history is not None and not (
        isinstance(history, list)
        and all(isinstance(t, dict) for t in history)
    ):
        raise HTTPException(status_code=400, detail="history 须为 {role,content} 数组")
    try:
        return run_backtest_chat(
            user_id=int(user["id"]),
            message=message,
            history=history or None,
        )
    except PermissionError as exc:
        raise _perm_http(exc) from exc
    except (ValueError, LlmError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
