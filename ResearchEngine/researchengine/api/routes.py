"""HTTP 路由：健康检查、回测与只读日线行情。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Response

from researchengine.api.market_data import get_daily_bars, get_symbols
from researchengine.api.ai_factor import generate_factor
from researchengine.api.ai_strategy import generate_strategy
from researchengine.api.ai_interpretation import interpret_backtest
from researchengine.api.runner import run_factor_backtest, run_strategy_backtest
from researchengine.api.schemas import (
    FactorBacktestRequest,
    FactorBacktestResponse,
    FactorInfo,
    FactorListResponse,
    HealthResponse,
    DailyBarsResponse,
    SymbolListResponse,
    StrategyBacktestRequest,
    StrategyBacktestResponse,
    StrategyInfo,
    StrategyListResponse,
    FactorGenerationRequest,
    FactorGenerationResponse,
    StrategyGenerationRequest,
    StrategyGenerationResponse,
    BacktestInterpretationRequest,
    BacktestInterpretationResponse,
)

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """健康检查。"""
    return HealthResponse(status="ok", version="2.0.0", engines=["native"])


@router.get("/factors", response_model=FactorListResponse)
def list_factors() -> FactorListResponse:
    """列内置因子（``alpha_library`` 的方法名 + docstring），供 UI 下拉。"""
    return FactorListResponse(factors=_builtin_factors())


@router.get("/strategies", response_model=StrategyListResponse)
def list_strategies() -> StrategyListResponse:
    """列出项目级策略目录中的当前版本，不执行策略源码。"""
    from researchengine.strategy_catalog import StrategyCatalog

    return StrategyListResponse(
        strategies=[StrategyInfo.model_validate(item) for item in StrategyCatalog().list_assets()]
    )


@router.get("/market-data/daily/{symbol}", response_model=DailyBarsResponse)
def daily_bars(
    symbol: str, start: date | None = None, end: date | None = None
) -> DailyBarsResponse:
    """返回指定股票在已发布历史数据中的完整日线 OHLC。"""
    return get_daily_bars(symbol, start, end)


@router.get("/market-data/symbols", response_model=SymbolListResponse)
def list_market_data_symbols() -> SymbolListResponse:
    """列出当前已发布市场数据中可查询的全部股票代码。"""
    return get_symbols()


@router.post("/ai/factor-generations", response_model=FactorGenerationResponse)
def generate_factor_draft(req: FactorGenerationRequest) -> FactorGenerationResponse:
    """自然语言 -> 经静态校验的因子函数草稿；不会执行代码或回测。"""
    return generate_factor(req)


@router.post("/ai/strategy-generations", response_model=StrategyGenerationResponse)
def generate_strategy_draft(req: StrategyGenerationRequest) -> StrategyGenerationResponse:
    """自然语言 -> 经静态校验的向量化策略草稿；不会执行代码或回测。"""
    return generate_strategy(req)


@router.post("/ai/backtest-interpretations", response_model=BacktestInterpretationResponse)
def interpret_backtest_result(req: BacktestInterpretationRequest) -> BacktestInterpretationResponse:
    """对成功的因子或向量化策略回测快照生成可追溯的研究解读。"""
    return interpret_backtest(req)


@router.post("/backtest/factor", response_model=FactorBacktestResponse)
def backtest_factor(req: FactorBacktestRequest, response: Response) -> FactorBacktestResponse:
    """因子回测：提交因子代码 + 参数 -> 跑回测 -> 返回指标 + 净值 + 因子分析。"""
    return run_factor_backtest(req, response)


@router.post("/backtest/strategy", response_model=StrategyBacktestResponse)
def backtest_strategy(req: StrategyBacktestRequest) -> StrategyBacktestResponse:
    """策略回测：提交自定义策略代码 -> 跑回测 -> 返回指标 + 净值。"""
    return run_strategy_backtest(req)


def _builtin_factors() -> "list[FactorInfo]":
    """枚举内置因子库的方法；加载失败返回空列表。"""
    try:
        from researchengine import FactorLoader
        from researchengine.api.runner import BUILTIN_FACTOR_LIBRARIES
        from researchengine.assets import factor_library_dir

        loader = FactorLoader(factor_dir=str(factor_library_dir()))
        factors = []
        for module_name in sorted(BUILTIN_FACTOR_LIBRARIES):
            library = loader.load(module_name)
            factors.extend(
                FactorInfo(name=n, description=(m.__doc__ or "").strip() or None)
                for n, m in library._factor_methods().items()
            )
        return factors
    except Exception:  # noqa: BLE001  无内置库或路径变化时不阻塞 API
        return []
