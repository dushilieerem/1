# -*- coding: utf-8 -*-
from __future__ import annotations

import mimetypes
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from app.bootstrap import FACTOR_DIR
from app.deps import optional_user, require_admin, require_db_user_id, require_user, soft_db_user_id
from services.factor.dashboard_store import query_metrics, read_job, set_verify_status, start_refresh
from services.factor.factor_store import add_custom_factor, delete_custom_factor, update_custom_factor
from services.factor.factor_trial import trial_via_re
from services.factor.re_backtest_jobs import (
    cancel_factor_backtest_job,
    get_factor_backtest_job,
    submit_factor_backtest,
)
from services.factor.re_factor_async_proxy import (
    proxy_cancel_factor_run,
    proxy_get_factor_run,
    proxy_submit_factor_backtest,
)
from services.factor.re_factor_catalog import (
    clear_re_catalog_cache,
    fetch_re_catalog,
    sync_all_scopes,
)
from services.factor.user_factor_store import custom_lib_source_for_user, filtered_index_yaml
from services.factor.user_library_store import (
    add_library_factor,
    create_user_library,
    delete_library_factor,
    delete_user_library,
    list_all_user_library_factors,
    list_library_factors,
    list_user_libraries,
    update_library_factor,
)

router = APIRouter(tags=["factor"])


@router.get("/api/factor/index")
def factor_index(user: dict | None = Depends(optional_user)) -> Response:
    try:
        from services.factor.user_factor_store import resolve_db_user_id

        owner_id = resolve_db_user_id(user) if user else None
    except Exception:
        owner_id = None
    raw = filtered_index_yaml(owner_id).encode("utf-8")
    return Response(content=raw, media_type="text/yaml; charset=utf-8")


@router.get("/api/factor/re-catalog")
def factor_re_catalog(
    fresh: str = Query("0"),
    all: str = Query("0"),
) -> JSONResponse:
    force = fresh in ("1", "true", "yes")
    include_all = all in ("1", "true", "yes")
    try:
        return JSONResponse(fetch_re_catalog(force=force, include_all=include_all))
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)


@router.post("/api/factor/re-catalog/sync")
def factor_re_catalog_sync(_admin: dict = Depends(require_admin)) -> JSONResponse:
    try:
        clear_re_catalog_cache()
        data = sync_all_scopes()
        all_data = data.get("all") or {}
        factors = all_data.get("factors") or []
        by_lib = Counter(str(f.get("library") or "") for f in factors)
        data["library_factor_counts"] = dict(sorted(by_lib.items()))
        if int(all_data.get("factor_count") or 0) <= 0:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "同步结果为空，未写入（请检查 RE 是否可达）",
                    "message": all_data.get("message"),
                    "detail": data,
                },
                status_code=502,
            )
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)


@router.get("/api/factor/re-backtest/{job_id}")
def factor_re_backtest_get(
    job_id: str, user: dict = Depends(require_user)
) -> JSONResponse:
    data = get_factor_backtest_job(job_id, user_id=int(user["id"]))
    code = 200
    if data.get("status") == "missing":
        code = 404
    elif data.get("status") == "forbidden":
        code = 403
    return JSONResponse(data, status_code=code)


@router.post("/api/factor/re-backtest")
def factor_re_backtest_post(
    body: dict[str, Any], user: dict = Depends(require_user)
) -> dict:
    try:
        return submit_factor_backtest(body, user_id=int(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/factor/re-backtest/{job_id}")
def factor_re_backtest_delete(
    job_id: str, user: dict = Depends(require_user)
) -> dict:
    return cancel_factor_backtest_job(job_id, user_id=int(user["id"]))


# —— 方案 A：薄转发对方异步因子回测（浏览器只打本机 /api）——


def _proxy_response(
    status: int, headers: dict[str, str], data: Any
) -> JSONResponse:
    return JSONResponse(content=data if data is not None else {}, status_code=status, headers=headers)


@router.post("/api/backtest/factor")
def backtest_factor_submit(
    body: dict[str, Any], _user: dict = Depends(require_user)
) -> JSONResponse:
    status, headers, data = proxy_submit_factor_backtest(body if isinstance(body, dict) else {})
    return _proxy_response(status, headers, data)


@router.get("/api/backtest/factor/{run_id}")
def backtest_factor_poll(
    run_id: str, _user: dict = Depends(require_user)
) -> JSONResponse:
    status, headers, data = proxy_get_factor_run(run_id)
    return _proxy_response(status, headers, data)


@router.delete("/api/backtest/factor/{run_id}")
def backtest_factor_cancel(
    run_id: str, _user: dict = Depends(require_user)
) -> JSONResponse:
    status, headers, data = proxy_cancel_factor_run(run_id)
    return _proxy_response(status, headers, data)


@router.get("/api/factor/libraries")
def factor_libraries(uid: int | None = Depends(soft_db_user_id)) -> dict:
    if uid is None:
        return {"ok": True, "libraries": []}
    return {"ok": True, "libraries": list_user_libraries(uid)}


@router.post("/api/factor/libraries")
def factor_create_library(
    body: dict[str, Any], uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        lib = create_user_library(uid, str(body.get("name") or ""))
        return {"ok": True, "library": lib}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/factor/libraries/{lib_id}")
def factor_delete_library(
    lib_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return delete_user_library(uid, lib_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/factor/libraries/factors")
def factor_all_library_factors(uid: int | None = Depends(soft_db_user_id)) -> dict:
    if uid is None:
        return {"ok": True, "factors": []}
    return {"ok": True, "factors": list_all_user_library_factors(uid)}


@router.get("/api/factor/libraries/{lib_id}/factors")
def factor_list_library_factors(
    lib_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return {"ok": True, "factors": list_library_factors(uid, lib_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/api/factor/libraries/{lib_id}/factors")
def factor_add_library_factor(
    lib_id: int,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        ready_raw = body.get("formulaReady", body.get("formula_ready"))
        formula_ready: bool | None
        if ready_raw is None:
            formula_ready = None
        else:
            formula_ready = bool(ready_raw)
        factor = add_library_factor(
            uid,
            lib_id,
            name=str(body.get("name") or ""),
            body=str(body.get("body") or body.get("expression") or ""),
            description=str(body.get("description") or ""),
            category_label=str(
                body.get("categoryLabel") or body.get("category") or "其他"
            ),
            formula_ready=formula_ready,
        )
        return {"ok": True, "factor": factor}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/factor/libraries/{lib_id}/factors/{factor_id}")
def factor_update_library_factor(
    lib_id: int,
    factor_id: int,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        ready_raw = body.get("formulaReady", body.get("formula_ready"))
        formula_ready: bool | None
        if "formulaReady" in body or "formula_ready" in body:
            formula_ready = bool(ready_raw)
        else:
            formula_ready = None
        factor = update_library_factor(
            uid,
            lib_id,
            factor_id,
            name=str(body.get("name") or "") if "name" in body else None,
            body=(
                str(body.get("body") or body.get("expression") or "")
                if ("body" in body or "expression" in body)
                else None
            ),
            description=(
                str(body.get("description"))
                if "description" in body
                else None
            ),
            category_label=(
                str(body.get("categoryLabel") or body.get("category") or "")
                if ("categoryLabel" in body or "category" in body)
                else None
            ),
            formula_ready=formula_ready,
        )
        return {"ok": True, "factor": factor}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/factor/libraries/{lib_id}/factors/{factor_id}")
def factor_delete_library_factor(
    lib_id: int,
    factor_id: int,
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return delete_library_factor(uid, lib_id, factor_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/factor/file/{name:path}")
def factor_file(
    name: str, uid: int | None = Depends(soft_db_user_id)
) -> Response:
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="bad path")
    if name == "custom_lib.py":
        raw = custom_lib_source_for_user(uid).encode("utf-8")
        return Response(content=raw, media_type="text/x-python; charset=utf-8")
    path = FACTOR_DIR / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    data = path.read_bytes()
    ctype = mimetypes.guess_type(str(path))[0] or "text/plain"
    if path.suffix in {".yaml", ".yml"}:
        ctype = "text/yaml; charset=utf-8"
    elif path.suffix == ".py":
        ctype = "text/x-python; charset=utf-8"
    return Response(content=data, media_type=ctype)


@router.get("/api/factor/dashboard")
def factor_dashboard(
    universe: str = Query("CSI300"),
    period: str = Query("3y"),
    filter_limit_up: str = Query("1"),
    filter_suspended: str = Query("1"),
    library: str | None = Query(None),
) -> dict:
    return query_metrics(
        universe=universe,
        period=period,
        filter_limit_up=filter_limit_up != "0",
        filter_suspended=filter_suspended != "0",
        library=library or None,
    )


@router.get("/api/factor/dashboard/status")
def factor_dashboard_status() -> dict:
    return read_job()


@router.post("/api/factor/dashboard/refresh")
def factor_dashboard_refresh(
    body: dict[str, Any] | None = None,
    admin: dict = Depends(require_admin),
) -> dict:
    """整批重跑 RE 回测是重活（数百次回测、按小时计），与校验状态同样限管理员。

    `skip_ok` 默认 False：面板「刷新指标」的语义是**重新计算**当前视图的全部因子
    （行情滚动后指标才会更新）。传 true 则退化为「只补算缺失行」，已算过的保留旧值。
    """
    body = body or {}
    try:
        return start_refresh(
            universe=str(body.get("universe") or "CSI300"),
            period=str(body.get("period") or "3y"),
            filter_limit_up=bool(body.get("filter_limit_up", True)),
            filter_suspended=bool(body.get("filter_suspended", True)),
            limit=int(body["limit"]) if body.get("limit") is not None else None,
            skip_ok=bool(body.get("skip_ok", False)),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/factor/dashboard/verify")
def factor_dashboard_verify(
    body: dict[str, Any], admin: dict = Depends(require_admin)
) -> dict:
    try:
        updated_by = str(
            admin.get("username") or admin.get("display_name") or admin.get("id") or ""
        )
        return set_verify_status(
            factor_name=str(body.get("factor_name") or ""),
            library_name=str(body.get("library_name") or "") or None,
            status=str(body.get("status") or ""),
            note=str(body.get("note") or ""),
            updated_by=updated_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/factor/custom")
def factor_custom_add(
    body: dict[str, Any], uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return add_custom_factor(
            user_id=uid,
            name=str(body.get("name") or ""),
            body=str(body.get("body") or ""),
            description=str(body.get("description") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/factor/custom/{name}")
def factor_custom_update(
    name: str,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return update_custom_factor(
            user_id=uid,
            name=name,
            body=str(body.get("body") or ""),
            description=str(body.get("description") or ""),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/factor/custom/{name}")
def factor_custom_delete(
    name: str, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return delete_custom_factor(user_id=uid, name=name)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/api/factor/custom/trial")
def factor_custom_trial(
    body: dict[str, Any], _user: dict = Depends(require_user)
) -> dict:
    try:
        return trial_via_re(
            body=str(body.get("body") or ""),
            factor_name=str(
                body.get("name") or body.get("factor_name") or "trial_factor"
            ),
            universe=str(body.get("universe") or "CSI300"),
            period=str(body.get("period") or "3m"),
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
