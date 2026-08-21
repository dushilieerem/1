"""因子回测路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.schemas.backtest import (
    FactorBacktestResponse,
    FactorBacktestRequest,
    FactorBacktestTaskResponse,
    FactorBacktestTaskSubmissionResponse,
)
from app.api.dependencies import get_experiment_manager
from app.services.experiment.manager import (
    ExperimentHandle,
    ExperimentManagerClosedError,
    ExperimentQueueFullError,
)
from app.services.factor.runner import submit_factor_backtest


router = APIRouter()


def _factor_task_response(manager, run_id: str) -> FactorBacktestTaskResponse:
    handle = manager.get(run_id)
    if not isinstance(handle, ExperimentHandle):
        raise HTTPException(status_code=404, detail=f"未找到因子回测任务: {run_id}")
    try:
        snapshot = handle.snapshot(include_result=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未找到因子回测任务: {run_id}") from exc
    status = snapshot["status"]
    error = snapshot["error"]
    result = snapshot.get("result")
    if status == "succeeded":
        if isinstance(result, tuple):
            result = result[0]
        result = FactorBacktestResponse.model_validate(result) if result is not None else None
        if result is None:
            status = "failed"
            error = "因子回测任务未返回结果"
        elif result.error:
            status = "failed"
            error = result.error
            result = None
    return FactorBacktestTaskResponse(
        run_id=snapshot["run_id"],
        status=status,
        created_at=snapshot["created_at"],
        started_at=snapshot["started_at"],
        finished_at=snapshot["finished_at"],
        cancel_requested=snapshot["cancel_requested"],
        error=error,
        result=result,
    )


@router.post(
    "/backtest/factor",
    response_model=FactorBacktestTaskSubmissionResponse,
    status_code=202,
)
async def backtest_factor(
    req: FactorBacktestRequest,
    response: Response,
    manager=Depends(get_experiment_manager),
) -> FactorBacktestTaskSubmissionResponse:
    try:
        handle = submit_factor_backtest(req, manager)
        snapshot = handle.snapshot()
        poll_url = f"/api/backtest/factor/{handle.run_id}"
        response.headers["Location"] = poll_url
        response.headers["Retry-After"] = "1"
        return FactorBacktestTaskSubmissionResponse(
            run_id=handle.run_id,
            status=snapshot["status"],
            poll_url=poll_url,
            created_at=snapshot["created_at"],
        )
    except ExperimentQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "1"}) from exc
    except ExperimentManagerClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/backtest/factor/{run_id}", response_model=FactorBacktestTaskResponse)
def get_factor_backtest(
    run_id: str,
    manager=Depends(get_experiment_manager),
) -> FactorBacktestTaskResponse:
    return _factor_task_response(manager, run_id)


@router.delete("/backtest/factor/{run_id}", response_model=FactorBacktestTaskResponse)
def cancel_factor_backtest(
    run_id: str,
    manager=Depends(get_experiment_manager),
) -> FactorBacktestTaskResponse:
    handle = manager.get(run_id)
    if not isinstance(handle, ExperimentHandle):
        raise HTTPException(status_code=404, detail=f"未找到因子回测任务: {run_id}")
    try:
        handle.cancel()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未找到因子回测任务: {run_id}") from exc
    return _factor_task_response(manager, run_id)


__all__ = ["router", "_factor_task_response"]
