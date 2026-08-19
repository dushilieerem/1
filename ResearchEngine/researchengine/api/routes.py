"""HTTP 路由：健康检查、回测与只读日线行情。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request, Response

from researchengine.api.market_data import (
    get_daily_bars,
    get_index_constituents,
    get_indices,
    get_symbols,
)
from researchengine.api.ai_factor import generate_factor
from researchengine.api.ai_strategy import generate_strategy
from researchengine.api.ai_interpretation import interpret_backtest
from researchengine.api.runner import (
    run_factor_backtest_async,
    run_strategy_backtest_async,
    submit_factor_backtest,
    submit_strategy_backtest,
)
from researchengine.manager import (
    ExperimentManagerClosedError,
    ExperimentQueueFullError,
)
from researchengine.api.schemas import (
    FactorBacktestRequest,
    FactorBacktestResponse,
    FactorInfo,
    FactorLibraryInfo,
    FactorLibraryListResponse,
    FactorListResponse,
    HealthResponse,
    DailyBarsResponse,
    IndexConstituentsResponse,
    IndexListResponse,
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
    ExperimentRunResponse,
    ExperimentSubmissionResponse,
)

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """健康检查。"""
    return HealthResponse(status="ok", version="2.0.0", engines=["native"])


@router.get("/factor-libraries", response_model=FactorLibraryListResponse)
def list_factor_libraries() -> FactorLibraryListResponse:
    """列出 ``index.yaml`` 中登记的全部内置因子库。"""
    try:
        from researchengine.api.runner import _builtin_factor_library_index

        libraries = []
        for library_name, metadata in sorted(_builtin_factor_library_index().items()):
            tags = metadata.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            factor_count = metadata.get("factor_count", 0)
            if not isinstance(factor_count, int) or isinstance(factor_count, bool):
                factor_count = 0
            libraries.append(
                FactorLibraryInfo(
                    name=library_name,
                    description=metadata.get("description"),
                    factor_count=factor_count,
                    tags=[tag for tag in tags if isinstance(tag, str)],
                )
            )
        return FactorLibraryListResponse(libraries=libraries)
    except Exception as exc:  # noqa: BLE001 - 目录不可用时返回明确服务错误
        raise HTTPException(status_code=503, detail=f"因子库目录不可用: {exc}") from exc


@router.get("/factors/{library_name}", response_model=FactorListResponse)
def list_library_factors(library_name: str) -> FactorListResponse:
    """列出指定内置因子库中的全部因子。"""
    try:
        from researchengine.api.runner import builtin_factor_library_names

        if library_name not in builtin_factor_library_names():
            raise HTTPException(status_code=404, detail=f"未找到内置因子库: {library_name}")
        factors = _builtin_factors(library_name)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 因子库加载失败不得伪造目录
        raise HTTPException(
            status_code=503,
            detail=f"因子库 {library_name!r} 不可用: {exc}",
        ) from exc
    return FactorListResponse(library_name=library_name, factors=factors)


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


@router.get("/market-data/indices", response_model=IndexListResponse)
def list_market_data_indices() -> IndexListResponse:
    """列出当前已发布市场数据中可查询的全部内置股指。"""
    return get_indices()


@router.get(
    "/market-data/indices/{code}/constituents",
    response_model=IndexConstituentsResponse,
)
def list_index_constituents(code: str) -> IndexConstituentsResponse:
    """返回指定股指在当前数据版本中的最新一期成分股。"""
    return get_index_constituents(code)


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
async def backtest_factor(
    req: FactorBacktestRequest,
    request: Request,
    response: Response,
) -> FactorBacktestResponse:
    """因子回测：提交因子代码 + 参数 -> 跑回测 -> 返回指标 + 净值 + 因子分析。"""
    manager = request.app.state.experiment_manager
    try:
        return await run_factor_backtest_async(req, response, manager)
    except ExperimentQueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "1"},
        ) from exc
    except ExperimentManagerClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/backtest/strategy", response_model=StrategyBacktestResponse)
async def backtest_strategy(
    req: StrategyBacktestRequest,
    request: Request,
) -> StrategyBacktestResponse:
    """策略回测：提交自定义策略代码 -> 跑回测 -> 返回指标 + 净值。"""
    manager = request.app.state.experiment_manager
    try:
        return await run_strategy_backtest_async(req, manager)
    except ExperimentQueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "1"},
        ) from exc
    except ExperimentManagerClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _experiment_response(manager, run_id: str) -> ExperimentRunResponse:
    handle = manager.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"未找到回测任务: {run_id}")

    snapshot = handle.snapshot(include_result=True)
    metadata = snapshot.get("metadata") or {}
    experiment_type = metadata.get("type")
    if experiment_type not in {"factor", "strategy"}:
        raise HTTPException(status_code=500, detail="回测任务缺少有效类型")

    raw_result = snapshot.pop("result", None)
    if isinstance(raw_result, tuple) and raw_result:
        raw_result = raw_result[0]
    if raw_result is not None and hasattr(raw_result, "model_dump"):
        raw_result = raw_result.model_dump(mode="json")
    snapshot["experiment_type"] = experiment_type
    snapshot["result"] = raw_result
    return ExperimentRunResponse.model_validate(snapshot)


@router.post(
    "/experiments/factor",
    response_model=ExperimentSubmissionResponse,
    status_code=202,
)
async def submit_factor_experiment(
    req: FactorBacktestRequest,
    request: Request,
) -> ExperimentSubmissionResponse:
    """提交异步因子回测任务，立即返回 ``run_id``。"""
    manager = request.app.state.experiment_manager
    try:
        handle = submit_factor_backtest(req, manager)
    except ExperimentQueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "1"},
        ) from exc
    except ExperimentManagerClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    snapshot = handle.snapshot()
    return ExperimentSubmissionResponse(
        run_id=handle.run_id,
        experiment_type="factor",
        status=snapshot["status"],
        metadata=snapshot["metadata"],
    )


@router.post(
    "/experiments/strategy",
    response_model=ExperimentSubmissionResponse,
    status_code=202,
)
async def submit_strategy_experiment(
    req: StrategyBacktestRequest,
    request: Request,
) -> ExperimentSubmissionResponse:
    """提交异步策略回测任务，立即返回 ``run_id``。"""
    manager = request.app.state.experiment_manager
    try:
        handle = submit_strategy_backtest(req, manager)
    except ExperimentQueueFullError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": "1"},
        ) from exc
    except ExperimentManagerClosedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    snapshot = handle.snapshot()
    return ExperimentSubmissionResponse(
        run_id=handle.run_id,
        experiment_type="strategy",
        status=snapshot["status"],
        metadata=snapshot["metadata"],
    )


@router.get("/experiments/{run_id}", response_model=ExperimentRunResponse)
def get_experiment(run_id: str, request: Request) -> ExperimentRunResponse:
    """查询异步回测状态；完成后同时返回结构化结果。"""
    return _experiment_response(request.app.state.experiment_manager, run_id)


@router.delete("/experiments/{run_id}", response_model=ExperimentRunResponse)
def cancel_experiment(run_id: str, request: Request) -> ExperimentRunResponse:
    """取消仍在排队的回测任务。运行中的线程只能记录取消请求。"""
    manager = request.app.state.experiment_manager
    handle = manager.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"未找到回测任务: {run_id}")
    handle.cancel()
    return _experiment_response(manager, run_id)


def _builtin_factors(library_name: str | None = None) -> "list[FactorInfo]":
    """枚举一个或全部内置因子库的方法；兼容测试和内部调用。"""
    try:
        from researchengine.api.runner import (
            _load_builtin_factor_library,
            builtin_factor_library_names,
        )

        factors = []
        library_names = (
            (library_name,)
            if library_name is not None
            else builtin_factor_library_names()
        )
        for current_library_name in library_names:
            _loader, library = _load_builtin_factor_library(current_library_name)
            factors.extend(
                FactorInfo(name=n, description=(m.__doc__ or "").strip() or None)
                for n, m in library._factor_methods().items()
            )
        return factors
    except Exception:  # noqa: BLE001  无内置库或路径变化时不阻塞 API
        if library_name is not None:
            raise
        return []
