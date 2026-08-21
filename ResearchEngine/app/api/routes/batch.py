"""每日因子回测批量路由。"""

from __future__ import annotations

from datetime import date
import json

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.backtest import (
    FactorBacktestBatchListResponse,
    FactorBacktestBatchResponse,
    FactorBacktestBatchSubmissionResponse,
    FactorBacktestBatchTriggerRequest,
    FactorBacktestFactorListResponse,
    FactorBacktestFactorRunResponse,
    FactorBacktestHistoryResponse,
)
from app.services.daily_factor_backtest import (
    DailyFactorBacktestCoordinator,
    DailyFactorBacktestProfile,
    DailyFactorBacktestQuery,
)
from app.api.dependencies import get_daily_factor_backtest_coordinator


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


def _query() -> DailyFactorBacktestQuery:
    return DailyFactorBacktestQuery()


@router.get("/factor-backtests/batches", response_model=FactorBacktestBatchListResponse)
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


@router.get("/factor-backtests/batches/{batch_id}", response_model=FactorBacktestBatchResponse)
def get_factor_backtest_batch(batch_id: str) -> FactorBacktestBatchResponse:
    row = _query().get_batch(batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"未找到因子回测批次: {batch_id}")
    return FactorBacktestBatchResponse.model_validate(_batch_payload(row))


@router.get("/factor-backtests/batches/{batch_id}/factors", response_model=FactorBacktestFactorListResponse)
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


@router.get("/factor-backtests/factors/{library_name}/{factor_name}/history", response_model=FactorBacktestHistoryResponse)
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
    "/internal/factor-backtests/batches",
    response_model=FactorBacktestBatchSubmissionResponse,
    status_code=202,
)
async def trigger_factor_backtest_batch(
    req: FactorBacktestBatchTriggerRequest,
    coordinator: DailyFactorBacktestCoordinator = Depends(
        get_daily_factor_backtest_coordinator
    ),
) -> FactorBacktestBatchSubmissionResponse:
    profile = DailyFactorBacktestProfile(as_of_date=req.as_of_date)
    result = await coordinator.run(profile, force_retry=req.force_retry, dry_run=req.dry_run)
    batch_id = result.get("id") if isinstance(result, dict) else None
    return FactorBacktestBatchSubmissionResponse(
        batch_id=str(batch_id) if batch_id else None,
        status=str(result.get("status", "accepted")) if isinstance(result, dict) else "accepted",
        query_url=f"/api/factor-backtests/batches/{batch_id}" if batch_id else None,
    )


__all__ = ["router"]
