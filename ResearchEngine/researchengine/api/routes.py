"""HTTP 路由：``/api/health``、``/api/backtest/factor``、``/api/backtest/strategy``。"""

from __future__ import annotations

from fastapi import APIRouter, Response

from researchengine.api.runner import run_factor_backtest, run_strategy_backtest
from researchengine.api.schemas import (
    FactorBacktestRequest,
    FactorBacktestResponse,
    FactorInfo,
    FactorListResponse,
    HealthResponse,
    StrategyBacktestRequest,
    StrategyBacktestResponse,
)

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """健康检查。"""
    return HealthResponse(status="ok", version="2.0.0", engines=["native", "vectorbt"])


@router.get("/factors", response_model=FactorListResponse)
def list_factors() -> FactorListResponse:
    """列内置因子（``alpha_library`` 的方法名 + docstring），供 UI 下拉。"""
    return FactorListResponse(factors=_builtin_factors())


@router.post("/backtest/factor", response_model=FactorBacktestResponse)
def backtest_factor(req: FactorBacktestRequest, response: Response) -> FactorBacktestResponse:
    """因子回测：提交因子代码 + 参数 -> 跑回测 -> 返回指标 + 净值 + 因子分析。"""
    return run_factor_backtest(req, response)


@router.post("/backtest/strategy", response_model=StrategyBacktestResponse)
def backtest_strategy(req: StrategyBacktestRequest) -> StrategyBacktestResponse:
    """策略回测：提交自定义策略代码 -> 跑回测 -> 返回指标 + 净值。"""
    return run_strategy_backtest(req)


def _builtin_factors() -> "list[FactorInfo]":
    """枚举 ``alpha_library`` 的因子方法；加载失败返回空列表。"""
    try:
        from researchengine import FactorLoader
        from researchengine.assets import factor_library_dir

        loader = FactorLoader(factor_dir=str(factor_library_dir()))
        library = loader.load("alpha_library")
        methods = library._factor_methods()
        return [
            FactorInfo(name=n, description=(m.__doc__ or "").strip() or None)
            for n, m in methods.items()
        ]
    except Exception:  # noqa: BLE001  无内置库或路径变化时不阻塞 API
        return []
