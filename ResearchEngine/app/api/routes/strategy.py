"""策略回测路由。"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_experiment_manager
from app.schemas.backtest import StrategyBacktestRequest, StrategyBacktestResponse
from app.services.experiment.manager import ExperimentManagerClosedError, ExperimentQueueFullError
from app.services.factor.runner import run_strategy_backtest_async


router = APIRouter()


@router.post("/backtest/strategy", response_model=StrategyBacktestResponse)
async def backtest_strategy(
    req: StrategyBacktestRequest,
    manager=Depends(get_experiment_manager),
) -> StrategyBacktestResponse:
    try:
        return await run_strategy_backtest_async(req, manager=manager)
    except ExperimentQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "1"}) from exc
    except ExperimentManagerClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


__all__ = ["router"]
