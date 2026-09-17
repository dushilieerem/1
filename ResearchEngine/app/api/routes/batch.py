"""因子批量回测路由。"""

from __future__ import annotations

from datetime import date
import json

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.backtest import (
    FactorBacktestBatchListResponse,
    FactorBacktestBatchResponse,
    FactorBacktestBatchTaskResponse,
    FactorBacktestBatchTaskSubmissionResponse,
    FactorBacktestBatchTriggerRequest,
    FactorBacktestFactorListResponse,
    FactorBacktestFactorRunResponse,
    FactorBacktestHistoryResponse,
)
from app.services.factor_backtest_batch.coordinator import FactorBacktestBatchCoordinator
from app.models.factor_batch import FactorBacktestBatchProfile
from app.services.factor_backtest_batch.query import FactorBacktestBatchQuery
from app.services.factor_backtest_batch.task_registry import (
    FactorBacktestBatchTaskRegistry,
    FactorBacktestBatchTaskRegistryClosedError,
)
from app.api.dependencies import (
    get_factor_backtest_batch_coordinator,
    get_factor_backtest_batch_task_registry,
)


router = APIRouter()


def _batch_payload(row: dict) -> dict:
    payload = dict(row)
    raw_profile = payload.pop("profile_json", "{}")
    try:
        payload["profile"] = json.loads(raw_profile) if isinstance(raw_profile, str) else raw_profile
    except (TypeError, ValueError):
        payload["profile"] = {}
    return payload


def _factor_payload(row: dict) -> dict:
    payload = dict(row)
    payload["quantile_metrics"] = payload.get("quantile_metrics") or []
    return payload


def _query() -> FactorBacktestBatchQuery:
    return FactorBacktestBatchQuery()


@router.get("/factor-backtest-batches", response_model=FactorBacktestBatchListResponse)
def list_factor_backtest_batches(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    as_of_date: date | None = None,
    status: str | None = None,
) -> FactorBacktestBatchListResponse:
    rows = _query().list_batches(
        limit=limit,
        offset=offset,
        as_of_date=as_of_date.isoformat() if as_of_date else None,
        status=status,
    )
    return FactorBacktestBatchListResponse(
        batches=[FactorBacktestBatchResponse.model_validate(_batch_payload(row)) for row in rows]
    )


@router.get("/factor-backtest-batches/{batch_id}", response_model=FactorBacktestBatchResponse)
def get_factor_backtest_batch(batch_id: str) -> FactorBacktestBatchResponse:
    row = _query().get_batch(batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"未找到因子回测批次: {batch_id}")
    return FactorBacktestBatchResponse.model_validate(_batch_payload(row))


@router.get("/factor-backtest-batches/{batch_id}/factors", response_model=FactorBacktestFactorListResponse)
def list_factor_backtest_runs(
    batch_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    library_name: str | None = None,
    factor_name: str | None = None,
) -> FactorBacktestFactorListResponse:
    query = _query()
    if query.get_batch(batch_id) is None:
        raise HTTPException(status_code=404, detail=f"未找到因子回测批次: {batch_id}")
    rows = query.list_factor_runs(
        batch_id,
        limit=limit,
        offset=offset,
        status=status,
        library_name=library_name,
        factor_name=factor_name,
    )
    return FactorBacktestFactorListResponse(
        factors=[FactorBacktestFactorRunResponse.model_validate(_factor_payload(row)) for row in rows]
    )


@router.get("/factor-backtest-batches/factors/{library_name}/{factor_name}/history", response_model=FactorBacktestHistoryResponse)
def factor_backtest_history(
    library_name: str,
    factor_name: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> FactorBacktestHistoryResponse:
    rows = _query().factor_history(library_name, factor_name, limit=limit, offset=offset)
    return FactorBacktestHistoryResponse(
        history=[FactorBacktestFactorRunResponse.model_validate(_factor_payload(row)) for row in rows]
    )


@router.post(
    "/internal/factor-backtest-batches",
    response_model=FactorBacktestBatchTaskSubmissionResponse,
    status_code=202,
)
async def trigger_factor_backtest_batch(
    req: FactorBacktestBatchTriggerRequest,
    coordinator: FactorBacktestBatchCoordinator = Depends(
        get_factor_backtest_batch_coordinator
    ),
    task_registry: FactorBacktestBatchTaskRegistry = Depends(
        get_factor_backtest_batch_task_registry
    ),
) -> FactorBacktestBatchTaskSubmissionResponse:
    profile = FactorBacktestBatchProfile(
        as_of_date=req.as_of_date,
        filter_suspended=req.filter_suspended,
        filter_limit_up=req.filter_limit_up,
        winsorize=req.winsorize,
        standardize=req.standardize,
    )
    try:
        task = task_registry.submit(
            coordinator,
            profile,
            force_retry=req.force_retry,
            dry_run=req.dry_run,
        )
    except FactorBacktestBatchTaskRegistryClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    task_id = str(task["task_id"])
    return FactorBacktestBatchTaskSubmissionResponse(
        task_id=task_id,
        status=task["status"],
        poll_url=f"/api/factor-backtest-batch-tasks/{task_id}",
        created_at=float(task["created_at"]),
    )


@router.get(
    "/factor-backtest-batch-tasks/{task_id}",
    response_model=FactorBacktestBatchTaskResponse,
)
def get_factor_backtest_batch_task(
    task_id: str,
    task_registry: FactorBacktestBatchTaskRegistry = Depends(
        get_factor_backtest_batch_task_registry
    ),
) -> FactorBacktestBatchTaskResponse:
    task = task_registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"未找到因子批量回测任务: {task_id}")
    return FactorBacktestBatchTaskResponse.model_validate(task)


__all__ = ["router"]
