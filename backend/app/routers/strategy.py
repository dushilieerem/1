# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.deps import require_admin, require_db_user_id, require_user
from services.strategy.builtin_strategies_store import (
    get_builtin_strategy,
    list_builtin_strategies_from_db,
    sync_builtin_strategies_from_re,
)
from services.strategy import re_capabilities
from services.strategy.joinquant import build_re_payload
from services.strategy.joinquant import precheck as joinquant_precheck
from services.core.re_http_gateway import forward_re
from services.strategy.strategy_store import (
    create_project as create_strategy_project,
    delete_project as delete_strategy_project,
    delete_run as delete_strategy_run,
    get_project as get_strategy_project,
    get_run as get_strategy_run,
    list_all_runs as list_all_strategy_runs,
    list_projects as list_strategy_projects,
    list_runs as list_strategy_runs,
    save_run as save_strategy_run,
    update_run_flagged as update_strategy_run_flagged,
    update_run_remark as update_strategy_run_remark,
    upsert_project as upsert_strategy_project,
)
from services.strategy.strategy_plaza_store import (
    create_plaza_item,
    get_plaza_item,
    hide_plaza_item,
    list_plaza_items,
)
from services.strategy.user_strategy_library_store import (
    add_library_strategy,
    create_user_strategy_library,
    delete_library_strategy,
    delete_user_strategy_library,
    get_library_strategy_archive,
    get_library_strategy_version,
    list_library_strategies,
    list_library_strategy_versions,
    update_library_strategy,
    list_user_strategy_libraries,
    mark_library_strategy_detected,
)

router = APIRouter(tags=["strategy"])


@router.post("/api/strategy/precheck")
def strategy_joinquant_precheck(body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict:
    """聚宽策略直跑前置校验：只做静态检查，不执行代码。"""
    return joinquant_precheck(
        str(body.get("code") or body.get("strategy_code") or ""),
        hint=(str(body.get("hint")).strip() if body.get("hint") else None),
    )


@router.get("/api/strategy/capabilities")
def strategy_capabilities(uid: int = Depends(require_db_user_id)) -> dict:
    """RE 聚宽方言能力清单（带缓存）；RE 不可用时返回 null，前端回退本地规则。"""
    return {"ok": True, "capabilities": re_capabilities.capabilities()}


@router.post("/api/strategy/joinquant/runs", status_code=202)
def strategy_joinquant_run(body: dict[str, Any], uid: int = Depends(require_db_user_id)) -> dict:
    """提交聚宽策略直跑（原始源码，不转写）。预检有阻断时拒绝提交。"""
    code = str(body.get("code") or body.get("strategy_code") or "")
    check = joinquant_precheck(code, hint=body.get("hint"))
    if not check["can_run_directly"]:
        raise HTTPException(
            status_code=400,
            detail={"error": "precheck_failed", "issues": check["issues"], "code_hash": check["code_hash"]},
        )
    start = str(body.get("start") or "").strip()
    end = str(body.get("end") or "").strip()
    if not start or not end:
        raise HTTPException(status_code=400, detail="缺少 start / end")

    payload = build_re_payload(
        source_code=code,
        start=start,
        end=end,
        universe=body.get("universe"),
        benchmark=body.get("benchmark"),
        initial_capital=body.get("initial_capital"),
        commission_rate=body.get("commission_rate"),
        stamp_tax=body.get("stamp_tax"),
        min_commission=body.get("min_commission"),
        slippage_rate=body.get("slippage_rate"),
        extra_symbols=body.get("extra_symbols"),
    )
    status, headers, data = forward_re("POST", "/api/backtest/strategy/async", payload=payload, timeout=30)
    if status == 429:
        raise HTTPException(status_code=429, detail="RE 队列已满，请稍后重试",
                            headers={"Retry-After": headers.get("Retry-After", "30")})
    if status == 503:
        raise HTTPException(status_code=503, detail="RE 正在关闭或不可用")
    if status not in (200, 202) or not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="RE 提交失败")
    run_id = str(data.get("run_id") or "")
    return {
        "ok": True,
        "run_id": run_id,
        "status": data.get("status"),
        "code_hash": check["code_hash"],
        "poll_url": f"/api/strategy/joinquant/runs/{run_id}" if run_id else None,
        "capabilities_version": check.get("capabilities_version"),
    }


@router.get("/api/strategy/joinquant/runs/{run_id}")
def strategy_joinquant_run_status(run_id: str, uid: int = Depends(require_db_user_id)) -> dict:
    status, _headers, data = forward_re("GET", f"/api/backtest/strategy/async/{run_id}", timeout=20)
    if status == 404:
        raise HTTPException(status_code=404, detail="回测任务已过期或不存在")
    if status != 200 or not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="RE 状态查询失败")
    return {"ok": True, **data}


@router.delete("/api/strategy/joinquant/runs/{run_id}")
def strategy_joinquant_run_cancel(run_id: str, uid: int = Depends(require_db_user_id)) -> dict:
    status, _headers, data = forward_re("DELETE", f"/api/backtest/strategy/async/{run_id}", timeout=20)
    if status == 404:
        raise HTTPException(status_code=404, detail="回测任务已过期或不存在")
    if status not in (200, 202) or not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="RE 取消失败")
    return {"ok": True, **data}


@router.get("/api/strategy/projects")
def strategy_list_projects(
    visible: str = Query("0"),
    uid: int = Depends(require_db_user_id),
) -> dict:
    visible_only = visible not in {"0", "false", "no"}
    return list_strategy_projects(uid, visible_only=visible_only)


@router.post("/api/strategy/projects")
def strategy_create_or_upsert(
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        if not body.get("id") and not body.get("config"):
            return create_strategy_project(
                uid,
                name=str(body.get("name") or body.get("description") or "未命名策略"),
                description=str(body.get("description") or body.get("name") or ""),
            )
        return upsert_strategy_project(uid, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/strategy/projects/{project_id}/runs")
def strategy_list_runs(
    project_id: str, uid: int = Depends(require_db_user_id)
) -> dict:
    return list_strategy_runs(uid, project_id)


@router.get("/api/strategy/projects/{project_id}")
def strategy_get_project(
    project_id: str, uid: int = Depends(require_db_user_id)
) -> dict:
    if "/" in project_id:
        raise HTTPException(status_code=404, detail="not found")
    try:
        return get_strategy_project(uid, project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.put("/api/strategy/projects/{project_id}")
def strategy_put_project(
    project_id: str,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    return upsert_strategy_project(uid, {**body, "id": project_id})


@router.delete("/api/strategy/projects/{project_id}")
def strategy_delete_project(
    project_id: str, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return delete_strategy_project(uid, project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/api/strategy/runs")
def strategy_save_run(
    body: dict[str, Any], uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return save_strategy_run(uid, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/strategy/runs")
def strategy_list_all_runs(uid: int = Depends(require_db_user_id)) -> dict:
    """当前用户全部回测报告（对标 GET /api/detect/runs）。"""
    return list_all_strategy_runs(uid)


@router.get("/api/strategy/runs/{run_id}/export.csv")
def strategy_export_run_csv(
    run_id: str, uid: int = Depends(require_db_user_id)
) -> Response:
    """导出单次回测摘要 CSV（P1-S04 首版）。"""
    try:
        data = get_strategy_run(uid, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    run = data.get("run") or {}
    result = run.get("result") or {}
    metrics = result.get("metrics") if isinstance(result, dict) else None
    if not isinstance(metrics, dict):
        metrics = {}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["field", "value"])
    for key in ("id", "name", "description", "finishedAt", "elapsedSec", "verified"):
        writer.writerow([key, run.get(key)])
    for key, value in sorted(metrics.items()):
        writer.writerow([f"metrics.{key}", value])
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="strategy-{run_id}.csv"'},
    )


@router.patch("/api/strategy/runs/{run_id}")
def strategy_patch_run(
    run_id: str,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    has_remark = "remark" in body
    has_flagged = "flagged" in body
    if not has_remark and not has_flagged:
        raise HTTPException(status_code=400, detail="缺少 remark 或 flagged")
    try:
        if has_flagged:
            return update_strategy_run_flagged(uid, run_id, bool(body.get("flagged")))
        return update_strategy_run_remark(uid, run_id, str(body.get("remark") or ""))
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/strategy/runs/{run_id}")
def strategy_get_run(run_id: str, uid: int = Depends(require_db_user_id)) -> dict:
    try:
        return get_strategy_run(uid, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.delete("/api/strategy/runs/{run_id}")
def strategy_delete_run(
    run_id: str, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return delete_strategy_run(uid, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/strategy/library")
def strategy_builtin_list(_user: dict = Depends(require_user)) -> dict:
    """内置策略目录：读 PG `builtin_strategies`（全站共享，与用户库隔离）。"""
    try:
        return list_builtin_strategies_from_db()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/strategy/library/sync")
def strategy_builtin_sync(_admin: dict = Depends(require_admin)) -> dict:
    """管理员：从 ResearchEngine 目录全量同步 PG 镜像。"""
    try:
        data = sync_builtin_strategies_from_re()
        if int(data.get("upserted") or 0) <= 0:
            raise HTTPException(
                status_code=502,
                detail="ResearchEngine 同步结果为空，未写入",
            )
        return {**data, "ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/api/strategy/library/{strategy_id}")
def strategy_builtin_source(
    strategy_id: str,
    _user: dict = Depends(require_user),
) -> dict:
    if not strategy_id or "/" in strategy_id:
        raise HTTPException(status_code=400, detail="invalid strategy id")
    try:
        return get_builtin_strategy(strategy_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/strategy/libraries")
def strategy_user_libraries(uid: int = Depends(require_db_user_id)) -> dict:
    """仅当前登录用户的策略库。"""
    return {"ok": True, "libraries": list_user_strategy_libraries(uid)}


@router.post("/api/strategy/libraries")
def strategy_create_library(
    body: dict[str, Any], uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        lib = create_user_strategy_library(uid, str(body.get("name") or ""))
        return {"ok": True, "library": lib}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/strategy/libraries/{lib_id}")
def strategy_delete_library(
    lib_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return delete_user_strategy_library(uid, lib_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/strategy/libraries/{lib_id}/strategies")
def strategy_list_library_strategies(
    lib_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    """库内策略：校验 library 归属当前 user，防串库。"""
    try:
        return {"ok": True, "strategies": list_library_strategies(uid, lib_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/api/strategy/libraries/{lib_id}/strategies")
def strategy_add_library_strategy(
    lib_id: int,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        strat = add_library_strategy(
            uid,
            lib_id,
            name=str(body.get("name") or ""),
            body=str(body.get("body") or body.get("strategy_code") or ""),
            description=str(body.get("description") or ""),
            category_label=str(body.get("categoryLabel") or "其他"),
            code_id=str(body.get("codeId") or ""),
            source_run_id=str(
                body.get("sourceRunId") or body.get("source_run_id") or ""
            ),
            archive_request=body.get("archiveRequest") or body.get("archive_request"),
            archive_result=body.get("archiveResult") or body.get("archive_result"),
            archive_elapsed_sec=(
                body.get("archiveElapsedSec")
                if body.get("archiveElapsedSec") is not None
                else body.get("archive_elapsed_sec")
            ),
            archive_finished_at=(
                str(body.get("archiveFinishedAt") or body.get("archive_finished_at") or "")
                or None
            ),
        )
        return {"ok": True, "strategy": strat}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/strategy/libraries/{lib_id}/strategies/{strategy_id}")
def strategy_delete_library_strategy(
    lib_id: int,
    strategy_id: int,
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return delete_library_strategy(uid, lib_id, strategy_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.put("/api/strategy/library-strategies/{strategy_id}")
def strategy_update_library_strategy(
    strategy_id: int,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        strat = update_library_strategy(
            uid,
            strategy_id,
            name=body.get("name"),
            body=body.get("body") or body.get("code"),
            description=body.get("description"),
            category_label=body.get("categoryLabel") or body.get("category_label"),
        )
        return {"ok": True, "strategy": strat}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/strategy/library-strategies/{strategy_id}/mark-detected")
def strategy_library_mark_detected(
    strategy_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    """用户库策略：回测成功后清除「待检测」。"""
    try:
        strat = mark_library_strategy_detected(uid, strategy_id)
        return {"ok": True, "strategy": strat}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/strategy/library-strategies/{strategy_id}/versions")
def strategy_library_versions(
    strategy_id: int,
    limit: int = 50,
    uid: int = Depends(require_db_user_id),
) -> dict:
    """FEAT-017：库内策略版本历史（元数据）。"""
    try:
        return {
            "ok": True,
            "items": list_library_strategy_versions(uid, strategy_id, limit=limit),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/strategy/library-strategies/{strategy_id}/versions/{version_no}")
def strategy_library_version(
    strategy_id: int,
    version_no: int,
    uid: int = Depends(require_db_user_id),
) -> dict:
    """FEAT-017：读取指定版本的完整快照。"""
    try:
        return {"ok": True, "version": get_library_strategy_version(uid, strategy_id, version_no)}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/strategy/library-strategies/{strategy_id}/archive")
def strategy_library_archive(
    strategy_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return get_library_strategy_archive(uid, strategy_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/strategy/plaza")
def strategy_plaza_list(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str = Query(""),
    sort: str = Query("newest"),
    universe: str = Query(""),
) -> dict:
    """策略广场列表（公开，无需登录）。"""
    return list_plaza_items(
        limit=limit,
        offset=offset,
        q=q or None,
        sort=sort or None,
        universe=universe or None,
    )


@router.get("/api/strategy/plaza/{item_id}")
def strategy_plaza_get(
    item_id: int,
    bump: int = Query(1, ge=0, le=1),
) -> dict:
    item = get_plaza_item(item_id, bump_view=bool(bump))
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    return {"item": item}


@router.post("/api/strategy/plaza")
def strategy_plaza_create(
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        item = create_plaza_item(
            uid,
            title=str(body.get("title") or ""),
            body=str(body.get("body") or ""),
            snapshot=body.get("snapshot") if isinstance(body.get("snapshot"), dict) else {},
            source_run_id=str(body.get("source_run_id") or body.get("sourceRunId") or "")
            or None,
        )
        return {"item": item}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/strategy/plaza/{item_id}")
def strategy_plaza_hide(
    item_id: int,
    user: dict = Depends(require_user),
    uid: int = Depends(require_db_user_id),
) -> dict:
    is_admin = str(user.get("role") or "").lower() == "admin"
    ok = hide_plaza_item(item_id, uid, as_admin=is_admin)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}
