# -*- coding: utf-8 -*-
"""机构量化端接口：独立登录、量化会话与成员私有资产边界。

路径前缀 `/api/inst/quant/*` 只接受 `product=quant` 的机构令牌；
个人令牌、主观机构令牌都不能进入这里。量化角色对主观九工作区无权限。

资产复用现有 detect/strategy/factor/backtest/AI 服务，但归属固定取 quant
会话的 user_id；不接受客户端传 user/org 参数。第一期是成员私有（member_private），
不是机构共享。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.deps import require_quant_researcher, require_quant_user
from services.core.audit_log_store import write_audit
from services.core.env_config import env
from services.core.rate_limit import enforce_rate_limit
from services.factor.user_factor_store import resolve_db_user_id
from services.institution.inst_store import (
    login_quant,
    login_quant_payload,
    me_payload,
)

router = APIRouter(tags=["institution-quant"])


def _ip(request: Request) -> str | None:
    xf = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xf:
        return xf.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def _login_limit() -> int:
    try:
        return max(1, int(env("INST_LOGIN_RATE_LIMIT", "10") or "10"))
    except (TypeError, ValueError):
        return 10


def _quant_uid(ctx: dict[str, Any] = Depends(require_quant_researcher)) -> int:
    try:
        return resolve_db_user_id(ctx["user"])
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/api/inst/quant/auth/login")
def inst_quant_login(body: dict[str, Any], request: Request) -> dict:
    enforce_rate_limit(
        request, scope="inst.quant.auth.login", limit=_login_limit(), window_sec=60
    )
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    try:
        result = login_quant(username=username, password=password)
    except PermissionError as exc:
        write_audit(
            action="inst.quant.login_failed",
            username=username or None,
            module="institution_quant",
            method="POST",
            path="/api/inst/quant/auth/login",
            status_code=403,
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail=str(exc)[:200],
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        write_audit(
            action="inst.quant.login_failed",
            username=username or None,
            module="institution_quant",
            method="POST",
            path="/api/inst/quant/auth/login",
            status_code=401,
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail=str(exc)[:200],
        )
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    payload = login_quant_payload(result)
    user = payload.get("user") or {}
    write_audit(
        action="inst.quant.login",
        user_id=int(user["id"]) if user.get("id") else None,
        username=str(user.get("username") or username) or None,
        role=str(payload.get("role") or ""),
        module="institution_quant",
        method="POST",
        path="/api/inst/quant/auth/login",
        status_code=200,
        ip=_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail=f"机构量化端登录：{payload.get('org', {}).get('name_cn', '')} / {payload.get('role_label_cn', '')}",
    )
    return payload


@router.get("/api/inst/quant/me")
def inst_quant_me(ctx: dict[str, Any] = Depends(require_quant_user)) -> dict:
    return me_payload(ctx)


# ---------------------------------------------------------------- detect 适配


@router.get("/api/inst/quant/detect/projects")
def quant_detect_projects(
    visible: str = Query("0"), uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import detect

    return detect.detect_list_projects(visible=visible, uid=uid)


@router.post("/api/inst/quant/detect/projects")
def quant_detect_project_create(
    body: dict[str, Any] = Body(...), uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import detect

    return detect.detect_create_or_upsert(body=body, uid=uid)


@router.get("/api/inst/quant/detect/projects/{project_id}/runs")
def quant_detect_project_runs(
    project_id: str, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import detect

    return detect.detect_list_runs(project_id=project_id, uid=uid)


@router.get("/api/inst/quant/detect/projects/{project_id}")
def quant_detect_project_get(
    project_id: str, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import detect

    return detect.detect_get_project(project_id=project_id, uid=uid)


@router.put("/api/inst/quant/detect/projects/{project_id}")
def quant_detect_project_put(
    project_id: str,
    body: dict[str, Any] = Body(...),
    uid: int = Depends(_quant_uid),
    ctx: dict = Depends(require_quant_user),
) -> dict:
    from app.routers import detect
    from services.quant_factor.presentation import save_workbench
    try:
        saved=save_workbench(uid,int(ctx['org']['id']),project_id,body)
        return saved if saved is not None else detect.detect_put_project(project_id=project_id,body=body,uid=uid)
    except (ValueError,KeyError) as exc:
        raise HTTPException(status_code=409,detail=str(exc)) from exc


@router.delete("/api/inst/quant/detect/projects/{project_id}")
def quant_detect_project_delete(
    project_id: str, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import detect

    return detect.detect_delete_project(project_id=project_id, uid=uid)


@router.get("/api/inst/quant/detect/runs")
def quant_detect_runs(uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import detect

    return detect.detect_list_all_runs(uid=uid)


@router.post("/api/inst/quant/detect/runs")
def quant_detect_run_save(
    body: dict[str, Any] = Body(...), uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import detect

    return detect.detect_save_run(body=body, uid=uid)


@router.patch("/api/inst/quant/detect/runs/{run_id}")
def quant_detect_run_patch(
    run_id: str,
    body: dict[str, Any] = Body(...),
    uid: int = Depends(_quant_uid),
) -> dict:
    from app.routers import detect

    return detect.detect_patch_run(run_id=run_id, body=body, uid=uid)


@router.get("/api/inst/quant/detect/runs/{run_id}")
def quant_detect_run_get(run_id: str, uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import detect

    return detect.detect_get_run(run_id=run_id, uid=uid)


@router.delete("/api/inst/quant/detect/runs/{run_id}")
def quant_detect_run_delete(run_id: str, uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import detect

    return detect.detect_delete_run(run_id=run_id, uid=uid)


# ---------------------------------------------------------------- strategy 适配


@router.get("/api/inst/quant/strategy/projects")
def quant_strategy_projects(
    visible: str = Query("0"), uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_list_projects(visible=visible, uid=uid)


@router.post("/api/inst/quant/strategy/projects")
def quant_strategy_project_create(
    body: dict[str, Any] = Body(...), uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_create_or_upsert(body=body, uid=uid)


@router.get("/api/inst/quant/strategy/projects/{project_id}/runs")
def quant_strategy_project_runs(
    project_id: str, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_list_runs(project_id=project_id, uid=uid)


@router.get("/api/inst/quant/strategy/projects/{project_id}")
def quant_strategy_project_get(
    project_id: str, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_get_project(project_id=project_id, uid=uid)


@router.put("/api/inst/quant/strategy/projects/{project_id}")
def quant_strategy_project_put(
    project_id: str,
    body: dict[str, Any] = Body(...),
    uid: int = Depends(_quant_uid),
) -> dict:
    from app.routers import strategy

    return strategy.strategy_put_project(project_id=project_id, body=body, uid=uid)


@router.delete("/api/inst/quant/strategy/projects/{project_id}")
def quant_strategy_project_delete(
    project_id: str, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_delete_project(project_id=project_id, uid=uid)


@router.get("/api/inst/quant/strategy/runs")
def quant_strategy_runs(uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import strategy

    return strategy.strategy_list_all_runs(uid=uid)


@router.post("/api/inst/quant/strategy/runs")
def quant_strategy_run_save(
    body: dict[str, Any] = Body(...), uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_save_run(body=body, uid=uid)


@router.patch("/api/inst/quant/strategy/runs/{run_id}")
def quant_strategy_run_patch(
    run_id: str,
    body: dict[str, Any] = Body(...),
    uid: int = Depends(_quant_uid),
) -> dict:
    from app.routers import strategy

    return strategy.strategy_patch_run(run_id=run_id, body=body, uid=uid)


@router.get("/api/inst/quant/strategy/runs/{run_id}")
def quant_strategy_run_get(run_id: str, uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import strategy

    return strategy.strategy_get_run(run_id=run_id, uid=uid)


@router.delete("/api/inst/quant/strategy/runs/{run_id}")
def quant_strategy_run_delete(run_id: str, uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import strategy

    return strategy.strategy_delete_run(run_id=run_id, uid=uid)


@router.get("/api/inst/quant/strategy/library")
def quant_strategy_library(ctx: dict[str, Any] = Depends(require_quant_researcher)) -> dict:
    from app.routers import strategy

    return strategy.strategy_builtin_list(_user=ctx["user"])


@router.get("/api/inst/quant/strategy/library/{strategy_id}")
def quant_strategy_library_source(
    strategy_id: str, ctx: dict[str, Any] = Depends(require_quant_researcher)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_builtin_source(strategy_id=strategy_id, _user=ctx["user"])


@router.get("/api/inst/quant/strategy/libraries")
def quant_strategy_user_libraries(uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import strategy

    return strategy.strategy_user_libraries(uid=uid)


@router.post("/api/inst/quant/strategy/libraries")
def quant_strategy_user_library_create(
    body: dict[str, Any] = Body(...), uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_create_library(body=body, uid=uid)


@router.delete("/api/inst/quant/strategy/libraries/{lib_id}")
def quant_strategy_user_library_delete(
    lib_id: int, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_delete_library(lib_id=lib_id, uid=uid)


@router.get("/api/inst/quant/strategy/libraries/{lib_id}/strategies")
def quant_strategy_library_strategies(
    lib_id: int, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_list_library_strategies(lib_id=lib_id, uid=uid)


@router.post("/api/inst/quant/strategy/libraries/{lib_id}/strategies")
def quant_strategy_library_strategy_add(
    lib_id: int,
    body: dict[str, Any] = Body(...),
    uid: int = Depends(_quant_uid),
) -> dict:
    from app.routers import strategy

    return strategy.strategy_add_library_strategy(lib_id=lib_id, body=body, uid=uid)


@router.delete("/api/inst/quant/strategy/libraries/{lib_id}/strategies/{strategy_id}")
def quant_strategy_library_strategy_delete(
    lib_id: int, strategy_id: int, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_delete_library_strategy(
        lib_id=lib_id, strategy_id=strategy_id, uid=uid
    )


@router.get("/api/inst/quant/strategy/library-strategies/{strategy_id}/archive")
def quant_strategy_library_archive(
    strategy_id: int, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_library_archive(strategy_id=strategy_id, uid=uid)


@router.post(
    "/api/inst/quant/strategy/library-strategies/{strategy_id}/mark-detected"
)
def quant_strategy_library_mark_detected(
    strategy_id: int, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import strategy

    return strategy.strategy_library_mark_detected(strategy_id=strategy_id, uid=uid)


# ---------------------------------------------------------------- factor 适配


@router.get("/api/inst/quant/factor/libraries")
def quant_factor_libraries(uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import factor

    return factor.factor_libraries(uid=uid)


@router.post("/api/inst/quant/factor/libraries")
def quant_factor_library_create(
    body: dict[str, Any] = Body(...), uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import factor

    return factor.factor_create_library(body=body, uid=uid)


@router.delete("/api/inst/quant/factor/libraries/{lib_id}")
def quant_factor_library_delete(lib_id: int, uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import factor

    return factor.factor_delete_library(lib_id=lib_id, uid=uid)


@router.get("/api/inst/quant/factor/libraries/factors")
def quant_factor_all_factors(uid: int = Depends(_quant_uid)) -> dict:
    from app.routers import factor

    return factor.factor_all_library_factors(uid=uid)


@router.get("/api/inst/quant/factor/libraries/{lib_id}/factors")
def quant_factor_library_factors(
    lib_id: int, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import factor

    return factor.factor_list_library_factors(lib_id=lib_id, uid=uid)


@router.post("/api/inst/quant/factor/libraries/{lib_id}/factors")
def quant_factor_library_factor_add(
    lib_id: int,
    body: dict[str, Any] = Body(...),
    uid: int = Depends(_quant_uid),
) -> dict:
    from app.routers import factor

    return factor.factor_add_library_factor(lib_id=lib_id, body=body, uid=uid)


@router.put("/api/inst/quant/factor/libraries/{lib_id}/factors/{factor_id}")
def quant_factor_library_factor_update(
    lib_id: int,
    factor_id: int,
    body: dict[str, Any] = Body(...),
    uid: int = Depends(_quant_uid),
) -> dict:
    from app.routers import factor

    return factor.factor_update_library_factor(
        lib_id=lib_id, factor_id=factor_id, body=body, uid=uid
    )


@router.delete("/api/inst/quant/factor/libraries/{lib_id}/factors/{factor_id}")
def quant_factor_library_factor_delete(
    lib_id: int, factor_id: int, uid: int = Depends(_quant_uid)
) -> dict:
    from app.routers import factor

    return factor.factor_delete_library_factor(
        lib_id=lib_id, factor_id=factor_id, uid=uid
    )


# ---------------------------------------------------------------- backtest 适配


@router.post("/api/inst/quant/backtest/factor")
def quant_backtest_factor(
    body: dict[str, Any] = Body(...),
    ctx: dict[str, Any] = Depends(require_quant_researcher),
    uid: int = Depends(_quant_uid),
) -> JSONResponse:
    from app.routers import factor

    return factor.backtest_factor_submit(body=body, _user=ctx["user"], uid=uid)


@router.get("/api/inst/quant/backtest/factor/{run_id}")
def quant_backtest_factor_poll(
    run_id: str,
    ctx: dict[str, Any] = Depends(require_quant_researcher),
    uid: int = Depends(_quant_uid),
) -> JSONResponse:
    from app.routers import factor

    return factor.backtest_factor_poll(run_id=run_id, _user=ctx["user"], uid=uid)


@router.delete("/api/inst/quant/backtest/factor/{run_id}")
def quant_backtest_factor_cancel(
    run_id: str, ctx: dict[str, Any] = Depends(require_quant_researcher)
) -> JSONResponse:
    from app.routers import factor

    return factor.backtest_factor_cancel(run_id=run_id, _user=ctx["user"])


@router.post("/api/inst/quant/backtest/strategy")
def quant_backtest_strategy(
    body: dict[str, Any] = Body(...),
    ctx: dict[str, Any] = Depends(require_quant_researcher),
) -> JSONResponse:
    from app.routers import re_gateway

    return re_gateway.backtest_strategy_submit(body=body, _user=ctx["user"])


# ---------------------------------------------------------------- AI 适配


@router.post("/api/inst/quant/ai/factor-generations")
def quant_ai_factor_generation(
    body: dict[str, Any] = Body(...),
    ctx: dict[str, Any] = Depends(require_quant_researcher),
) -> dict[str, Any]:
    from services.quant_factor.generation import generate
    from services.quant_factor.policy import WorkflowError
    uid=_quant_uid(ctx)
    try:
        return generate(uid,int(ctx['org']['id']),None,'manual:'+str(uid)+':'+str(body.get('idempotency_key') or ''),body)
    except WorkflowError as exc:
        raise HTTPException(status_code=409,detail=str(exc)) from exc


@router.post("/api/inst/quant/ai/strategy-generations")
def quant_ai_strategy_generation(
    body: dict[str, Any] = Body(...),
    ctx: dict[str, Any] = Depends(require_quant_researcher),
) -> dict[str, Any]:
    from app.routers import ai_strategy_generation

    return ai_strategy_generation.ai_strategy_generations(body=body, _user=ctx["user"])
