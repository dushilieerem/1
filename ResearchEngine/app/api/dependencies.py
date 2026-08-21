"""HTTP 路由所需的应用级依赖。"""

from __future__ import annotations

from fastapi import Request

from app.services.daily_factor_backtest import DailyFactorBacktestCoordinator
from app.services.experiment.manager import ExperimentManager


def get_experiment_manager(request: Request) -> ExperimentManager:
    """返回 FastAPI lifespan 持有的唯一 ExperimentManager。"""

    manager = getattr(request.app.state, "experiment_manager", None)
    if not isinstance(manager, ExperimentManager):
        raise RuntimeError("ExperimentManager 尚未由 FastAPI lifespan 初始化")
    return manager


def get_daily_factor_backtest_coordinator(
    request: Request,
) -> DailyFactorBacktestCoordinator:
    """返回每日因子回测这一具体业务能力的协调器。"""

    coordinator = getattr(request.app.state, "daily_factor_backtest", None)
    if not isinstance(coordinator, DailyFactorBacktestCoordinator):
        raise RuntimeError("DailyFactorBacktestCoordinator 尚未由 FastAPI lifespan 初始化")
    return coordinator


__all__ = ["get_experiment_manager", "get_daily_factor_backtest_coordinator"]
