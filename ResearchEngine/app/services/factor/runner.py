"""核心：因子代码字符串 -> 回测 -> 序列化结果。

复用 :class:`app.services.factor.loader.FactorLoader`、
:class:`app.services.experiment.manager.ExperimentManager` 和
:class:`app.services.backtest.engine.BacktestEngine`，**不新写回测逻辑**，只把请求调用
包成可被 HTTP 路由调用的纯函数。

所有异常（语法错 / 导入错 / 运行错 / 因子名不存在）都会被转换为结构化错误。
内部同步包装函数仍返回 ``BacktestResponse.error``；异步 HTTP 任务路由将其映射为
``status=failed`` 和顶层 ``error``。
"""

from __future__ import annotations

import os
import asyncio
import hashlib
import json
import math
import time
from pathlib import Path

import pandas as pd

from app.schemas.backtest import (
    DateRange,
    FactorAnalysis,
    FactorBacktestMeta,
    FactorBacktestRequest,
    FactorBacktestResponse,
    StrategyBacktestRequest,
    StrategyBacktestResponse,
)
from app.services.factor.serializers import date_range_from, metrics_to_dict
from app.services.factor.backtest_support import (
    _BENCHMARK_FILES,
    _StrategyPanels,
    _asset_meta,
    _benchmark_equity,
    _custom_benchmark_equity,
    _declared_strategy_symbols,
    _load_benchmark_equity,
    _persisted_asset,
    _resolve_current_data_dir,
    _resolve_data_dir,
    _resolve_research_assets,
    _resolve_strategy_symbols,
)
from app.services.factor.result_serializers import (
    _compute_annual_returns,
    _compute_drawdowns,
    _compute_equity_with_drawdown,
    _display_instrument,
    _ic_points,
    _industry_equity_to_response,
    _industry_group_equity_to_response,
    _layered_equity_to_points,
    _rolling_ir_points,
    _sample_positions,
    _serialize_event_execution_timeline,
    _serialize_rebalance_logs,
    _serialize_vectorized_execution_timeline,
    _value_points,
)
from app.services.factor.metrics import (
    _compute_quantile_metrics,
    _finite_series,
    _geometric_annual_return,
    _safe_metric,
)
from app.services.experiment.base import Experiment
from app.services.data.engine import DataEngine
from app.services.experiment.strategy import StrategyExperiment
from app.services.backtest.engine import BacktestEngine
from app.services.factor.experiment import FactorBacktestExperiment
from app.services.factor.loader import (
    _builtin_factor_library_entry,
    _builtin_factor_library_index,
    _load_builtin_factor_library,
    _load_factor_from_builtin_library,
    _load_factor_from_code,
    _wrap_factor_code,
    builtin_factor_library_names,
)
from app.services.factor.sqlite_loader import (
    FactorDatabaseError,
    SQLiteFactorRepository,
)
from app.models.factor_backtest import FactorBacktestResult
from app.models.factor_backtest import FactorBacktestSpec
from app.services.experiment.manager import ExperimentHandle, ExperimentManager


def _cache_enabled() -> bool:
    return os.environ.get("SVQUANT_BACKTEST_CACHE_ENABLED", "true").lower() not in {
        "0", "false", "no",
    }


def _cache_int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _factor_cache():
    """构造因子回测缓存；缓存异常由调用方降级处理。"""
    from app.utils.paths import backtest_cache_dir
    from app.database.results.cache_impl import FileBacktestCache

    return FileBacktestCache(
        backtest_cache_dir(),
        ttl_days=_cache_int_env("SVQUANT_BACKTEST_CACHE_TTL_DAYS", 30),
        max_bytes=_cache_int_env("SVQUANT_BACKTEST_CACHE_MAX_BYTES", 10 * 1024**3),
    )


def _request_factor_source_hash(req: FactorBacktestRequest) -> str:
    sources: list[tuple[str, str]] = []
    if req.factor_code is not None:
        sources.append(("factor_code", hashlib.sha256(req.factor_code.encode("utf-8")).hexdigest()))
    database = None
    try:
        database = SQLiteFactorRepository()
    except (FileNotFoundError, FactorDatabaseError):
        # 迁移期允许没有外部数据库的旧开发环境继续使用文件库。
        pass
    for library_name in req.library_names:
        database_library = None
        if database is not None:
            try:
                database_library = database.get_library(library_name)
            except (KeyError, FileNotFoundError, FactorDatabaseError):
                database_library = None
        if database_library is not None and database is not None:
            if req.factor_code is None:
                try:
                    record = database.get_factor(
                        req.factor_name,
                        library_name=database_library.library_name,
                    )
                    source_hash = database.source_hash(record)
                except Exception:  # noqa: BLE001 - 统一在实际加载时报告不存在因子
                    source_hash = "missing"
            else:
                # 自定义源码可以复用 SQLite 库的方法；此时整个数据库/工具
                # 版本都属于源码的执行依赖。
                source_hash = database.catalog_signature()
            sources.append((library_name, source_hash))
            continue
        try:
            factor_dir, file_stem, _metadata = _builtin_factor_library_entry(library_name)
            path = factor_dir / f"{file_stem}.py"
            sources.append((library_name, hashlib.sha256(path.read_bytes()).hexdigest()))
        except Exception:
            sources.append((library_name, "missing"))
    # 内置单因子批量目录直接记录实现文件 SHA；单因子入口必须使用同一
    # 原始 SHA，才能让相同规格跨入口共享 spec/cache 身份。
    if len(sources) == 1:
        return sources[0][1]
    payload = json.dumps(sources, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _request_spec(req: FactorBacktestRequest) -> FactorBacktestSpec:
    universe = (
        tuple(req.universe_snapshot.symbols)
        if req.universe_snapshot is not None
        else req.universe
    )
    return FactorBacktestSpec(
        factor_name=req.factor_name,
        factor_source_hash=_request_factor_source_hash(req),
        factor_code=req.factor_code,
        library_names=tuple(req.library_names),
        universe=universe,
        universe_snapshot=req.universe_snapshot,
        start=req.start,
        end=req.end,
        benchmark=req.benchmark,
        benchmark_snapshot=req.benchmark_snapshot,
        portfolio_type=req.portfolio_type,
        rebalance_days=req.rebalance_days,
        groups=req.groups,
        commission_rate=req.commission_rate,
        stamp_tax=req.stamp_tax,
        slippage_rate=req.slippage_rate,
        filter_limit_up=req.filter_limit_up,
        filter_suspended=req.filter_suspended,
        # 兼容旧的总开关语义：核心流程只接收已经归一化的有效开关。
        filters_enabled=bool(req.filter_limit_up or req.filter_suspended),
        winsorize=req.winsorize,
        standardize=req.standardize,
        analysis_level=req.analysis_level,
        engine="native",
        strict_as_of=True,
    )


def _factor_cache_key(spec: FactorBacktestSpec, cache, *, data_context=None) -> str:
    if isinstance(spec, FactorBacktestRequest):
        spec = _request_spec(spec)
    data_dir = Path(
        getattr(data_context, "data_dir", None) or _resolve_data_dir(None)
    )
    release_id = getattr(data_context, "release_id", None)
    return cache.make_key(
        {
            **spec.computation_payload(),
            "data_release_id": release_id,
            "execution_version": spec.execution_version,
            "metric_version": spec.metric_version,
        },
        cache.data_fingerprint(data_dir),
    )


def _cache_value(value):
    """把标准结果中的 pandas/NumPy 值编码为稳定 JSON 结构。"""
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Series):
        return {
            "__type__": "series",
            "name": _cache_value(value.name),
            "index": [_cache_value(item) for item in value.index],
            "data": [_cache_value(item) for item in value.tolist()],
        }
    if isinstance(value, pd.DataFrame):
        return {
            "__type__": "dataframe",
            "index": [_cache_value(item) for item in value.index],
            "columns": [_cache_value(item) for item in value.columns],
            "data": [
                [_cache_value(item) for item in row]
                for row in value.to_numpy().tolist()
            ],
        }
    if isinstance(value, dict):
        return {str(key): _cache_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_cache_value(item) for item in value]
    if hasattr(value, "model_dump"):
        return _cache_value(value.model_dump(mode="json"))
    if hasattr(value, "item"):
        return _cache_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _restore_index(values: list, *, datetime_index: bool = True):
    if datetime_index and values:
        parsed = pd.to_datetime(values, errors="coerce")
        if not parsed.isna().any():
            return parsed
    return pd.Index(values)


def _restore_cache_value(value, *, datetime_index: bool = True):
    if not isinstance(value, dict):
        if isinstance(value, list):
            return [
                _restore_cache_value(item, datetime_index=datetime_index)
                for item in value
            ]
        return value
    value_type = value.get("__type__")
    if value_type == "series":
        return pd.Series(
            [
                _restore_cache_value(item, datetime_index=False)
                for item in value.get("data", [])
            ],
            index=_restore_index(
                value.get("index", []), datetime_index=datetime_index
            ),
            name=value.get("name"),
        )
    if value_type == "dataframe":
        return pd.DataFrame(
            [
                _restore_cache_value(row, datetime_index=False)
                for row in value.get("data", [])
            ],
            index=_restore_index(
                value.get("index", []), datetime_index=datetime_index
            ),
            columns=value.get("columns", []),
        )
    return {
        key: _restore_cache_value(item, datetime_index=datetime_index)
        for key, item in value.items()
    }


def _factor_request_from_spec(spec: FactorBacktestSpec) -> FactorBacktestRequest:
    """为批量缓存复用现有 HTTP 投影器构造等价 DTO。"""
    payload = {
        "factor_code": spec.factor_code,
        "library_name": (
            spec.library_names[0]
            if len(spec.library_names) == 1
            else list(spec.library_names)
        ),
        "factor_name": spec.factor_name,
        "start": spec.start,
        "end": spec.end,
        "portfolio_type": spec.portfolio_type,
        "rebalance_days": spec.rebalance_days,
        "groups": spec.groups,
        "benchmark": spec.benchmark,
        "commission_rate": spec.commission_rate,
        "stamp_tax": spec.stamp_tax,
        "slippage_rate": spec.slippage_rate,
        "filter_limit_up": spec.filter_limit_up,
        "filter_suspended": spec.filter_suspended,
        "winsorize": spec.winsorize,
        "standardize": spec.standardize,
        "analysis_level": spec.analysis_level,
    }
    if spec.universe_snapshot is not None:
        payload["universe_snapshot"] = spec.universe_snapshot
    else:
        payload["universe"] = str(spec.universe)
    if spec.benchmark_snapshot is not None:
        payload.pop("benchmark", None)
        payload["benchmark_snapshot"] = spec.benchmark_snapshot
    return FactorBacktestRequest(**payload)


def _factor_standard_report(
    execution: FactorBacktestResult,
    response: FactorBacktestResponse,
) -> dict:
    """生成 API 与批量任务共享的标准报告缓存载荷。"""
    result = execution.result_manager
    return {
        "cache_format": "factor-standard-report-v2",
        "standard": {
            "spec": execution.spec.to_dict(),
            "spec_hash": execution.spec_hash,
            "data_release_id": execution.data_release_id,
            "actual_end": execution.actual_end,
            "metrics": _cache_value(result.metrics),
            "factor_values": _cache_value(getattr(result, "factor_values", None)),
            "equity_curve": _cache_value(execution.equity_curve),
            "returns": _cache_value(execution.returns),
            "positions": _cache_value(execution.positions),
            "benchmark_equity": _cache_value(execution.benchmark_equity),
            "factor_analysis": _cache_value(execution.factor_analysis),
            "quantile_metrics": _cache_value(list(execution.quantile_metrics)),
            "predictive_metrics": _cache_value(execution.predictive_metrics),
            "meta": _cache_value(result.meta),
        },
        # HTTP 是标准结果的一个外围投影，保留它可以让现有 API 缓存命中零改动。
        "http_response": response.model_dump(mode="json"),
    }


def _factor_execution_from_standard_report(
    spec: FactorBacktestSpec,
    payload: dict,
) -> FactorBacktestResult | None:
    if payload.get("cache_format") != "factor-standard-report-v2":
        return None
    standard = payload.get("standard")
    if not isinstance(standard, dict):
        return None
    from app.services.results.manager import ResultManager

    actual_end = standard.get("actual_end")
    result = ResultManager(
        metrics=_restore_cache_value(
            standard.get("metrics", {}), datetime_index=False
        ),
        factor_values=_restore_cache_value(
            standard.get("factor_values"), datetime_index=True
        ),
        equity_curve=_restore_cache_value(
            standard.get("equity_curve"), datetime_index=True
        ),
        returns=_restore_cache_value(
            standard.get("returns"), datetime_index=True
        ),
        positions=_restore_cache_value(
            standard.get("positions"), datetime_index=True
        ),
        meta=_restore_cache_value(
            standard.get("meta", {}), datetime_index=False
        ),
    )
    result.factor_analysis = _restore_cache_value(
        standard.get("factor_analysis", {}), datetime_index=True
    )
    benchmark = _restore_cache_value(
        standard.get("benchmark_equity"), datetime_index=True
    )
    if result.equity_curve is None or benchmark is None:
        return None
    return FactorBacktestResult(
        spec=spec,
        result_manager=result,
        benchmark_equity=benchmark,
        quantile_metrics=tuple(
            _restore_cache_value(
                standard.get("quantile_metrics", []), datetime_index=False
            )
        ),
        predictive_metrics=_restore_cache_value(
            standard.get("predictive_metrics", {}), datetime_index=False
        ),
        data_release_id=standard.get("data_release_id"),
        actual_end=actual_end,
    )


def _run_cached_standard_factor_backtest(
    spec: FactorBacktestSpec,
    execute,
    *,
    data_context=None,
) -> FactorBacktestResult:
    """批量入口的缓存策略；计算仍由传入的统一 executor 回调完成。"""
    if not _cache_enabled():
        return execute()
    try:
        cache = _factor_cache()
        key = _factor_cache_key(spec, cache, data_context=data_context)
        cached = cache.get(key)
        if cached is not None:
            execution = _factor_execution_from_standard_report(spec, cached)
            if execution is not None:
                return execution
        with cache.lock(key) as acquired:
            cached = cache.get(key)
            if cached is not None:
                execution = _factor_execution_from_standard_report(spec, cached)
                if execution is not None:
                    return execution
    except Exception:  # noqa: BLE001 - 缓存故障不得改变回测可用性
        return execute()
    execution = execute()
    try:
        response = _serialize_factor_execution(
            _factor_request_from_spec(execution.spec),
            execution,
        )
        if acquired and response.error is None:
            cache.set(key, _factor_standard_report(execution, response))
    except Exception:  # noqa: BLE001 - 写缓存/投影失败不重复计算
        pass
    return execution


def _run_cached_factor_backtest(
    req: FactorBacktestRequest,
    cache,
    key: str,
    *,
    execute,
    data_context=None,
) -> tuple[FactorBacktestResponse, str]:
    """在线程池中完成缓存复核、文件锁协调和实际因子回测。"""
    try:
        cached = cache.get(key)
        if cached is not None:
            payload = (
                cached.get("http_response", cached)
                if isinstance(cached, dict)
                else cached
            )
            return FactorBacktestResponse.model_validate(payload), "HIT"

        with cache.lock(key) as acquired:
            cached = cache.get(key)
            if cached is not None:
                payload = (
                    cached.get("http_response", cached)
                    if isinstance(cached, dict)
                    else cached
                )
                return FactorBacktestResponse.model_validate(payload), "HIT"
    except Exception:  # noqa: BLE001 缓存不可用不得阻断研究回测
        execution = execute()
        return _serialize_factor_execution(req, execution), "BYPASS"
    execution = execute()
    result = _serialize_factor_execution(req, execution)
    if acquired and result.error is None:
        try:
            cache.set(key, _factor_standard_report(execution, result))
        except Exception:  # noqa: BLE001 写缓存失败不重复执行回测
            return result, "BYPASS"
    return result, "MISS"


def _factor_task_key(
    req: FactorBacktestRequest,
    *,
    data_release_id: str | None = None,
) -> str:
    """按统一规格生成进程内同规格去重键。"""

    return "factor-spec:" + _request_spec(req).identity(data_release_id=data_release_id)


def _run_factor_backtest_job(
    req: FactorBacktestRequest,
    *,
    spec: FactorBacktestSpec | None = None,
    execute=None,
    data_context=None,
) -> tuple[FactorBacktestResponse, str]:
    """在线程池中计算行情指纹、读取缓存并执行因子回测。"""

    if execute is None:
        # 旧内部调用兼容：正式 Manager 任务始终传入统一执行回调。
        return _run_factor_backtest_uncached(req, data_context=data_context), "BYPASS"
    spec = spec or _request_spec(req)

    if not _cache_enabled():
        return _serialize_factor_execution(req, execute()), "BYPASS"

    try:
        cache = _factor_cache()
        key = _factor_cache_key(spec, cache, data_context=data_context)
    except Exception:  # noqa: BLE001 缓存不可用不得阻断研究回测
        return _serialize_factor_execution(req, execute()), "BYPASS"
    return _run_cached_factor_backtest(
        req,
        cache,
        key,
        execute=execute,
        data_context=data_context,
    )


def submit_factor_backtest(
    req: FactorBacktestRequest,
    manager: ExperimentManager,
) -> ExperimentHandle[Any]:
    """只创建因子回测任务；缓存扫描和行情读取均在线程池中执行。"""

    spec = _request_spec(req)
    try:
        data_release_id = getattr(DataEngine.get_instance(), "release_id", "unknown")
    except Exception:  # noqa: BLE001 - 由 Manager.submit/worker 统一暴露运行时状态
        data_release_id = None
    engine = BacktestEngine()

    def run_policy(execute):
        return _run_factor_backtest_job(
            req,
            spec=spec,
            execute=execute,
            data_context=DataEngine.get_instance(),
        )

    return manager.submit(
        FactorBacktestExperiment(spec, engine=engine, run_policy=run_policy),
        key=_factor_task_key(req, data_release_id=data_release_id),
        lane="interactive",
        metadata={
            "type": "factor",
            "cache": "PENDING",
            "data_release_id": data_release_id,
            "spec_hash": spec.identity(data_release_id=data_release_id),
        },
    )


def _unpack_factor_result(
    handle: ExperimentHandle[Any], response=None
) -> FactorBacktestResponse:
    result, cache_status = handle.result()
    if response is not None:
        response.headers["X-SVQuant-Cache"] = cache_status
    return result


def run_factor_backtest(
    req: FactorBacktestRequest,
    response=None,
    *,
    manager: ExperimentManager,
) -> FactorBacktestResponse:
    """同步等待应用级 Manager 中的因子回测。"""
    return _unpack_factor_result(submit_factor_backtest(req, manager), response)


async def run_factor_backtest_async(
    req: FactorBacktestRequest,
    response=None,
    *,
    manager: ExperimentManager,
) -> FactorBacktestResponse:
    """HTTP 层使用的异步等待门面，不占用 FastAPI 通用线程池。"""
    handle = submit_factor_backtest(req, manager)
    result, cache_status = await asyncio.wrap_future(handle.future)
    if response is not None:
        response.headers["X-SVQuant-Cache"] = cache_status
    return result


def _run_factor_backtest_uncached(
    req: FactorBacktestRequest,
    *,
    data_context=None,
) -> FactorBacktestResponse:
    """旧内部同步门面；实际执行仍走统一规格和执行器。"""

    if data_context is None:
        return FactorBacktestResponse(
            error="BacktestEngine 必须由 ExperimentManager 提供行情上下文",
            meta=None,
        )
    spec = _request_spec(req)
    engine = BacktestEngine()
    try:
        DataEngine.configure_instance(data_context)
        execution = engine.run(spec)
    except Exception as exc:  # noqa: BLE001  保持旧同步响应契约
        return FactorBacktestResponse(
            error=f"{type(exc).__name__}: {exc}",
            meta=None,
        )
    return _serialize_factor_execution(req, execution)


def _serialize_factor_execution(
    req: FactorBacktestRequest,
    execution: FactorBacktestResult,
) -> FactorBacktestResponse:
    """把统一执行器结果投影为现有 HTTP 响应。"""
    started_at = time.perf_counter()
    result = execution.result_manager
    universe_snapshot = execution.spec.universe_snapshot
    benchmark_snapshot = execution.spec.benchmark_snapshot
    if universe_snapshot is not None or benchmark_snapshot is not None:
        result.meta["research_assets"] = {
            **({"universe": _persisted_asset(universe_snapshot)} if universe_snapshot else {}),
            **({"benchmark": _persisted_asset(benchmark_snapshot)} if benchmark_snapshot else {}),
        }
    periods_per_year = execution.spec.periods_per_year

    equity = result.equity_curve
    final_equity = (
        float(equity.iloc[-1]) if equity is not None and len(equity) else None
    )

    # 净值曲线（含回撤）
    equity_points = _compute_equity_with_drawdown(equity) if equity is not None else None

    # 回撤区间明细
    drawdowns = _compute_drawdowns(equity) if equity is not None else []

    # 分年收益
    annual_returns = _compute_annual_returns(equity) if equity is not None else []

    # 深度因子分析仅在请求显式要求时计算，避免其拖慢核心回测。
    metrics = metrics_to_dict(result.metrics)
    raw_strategy_returns = getattr(result, "returns", None)
    if raw_strategy_returns is not None:
        metrics["annual_return"] = _geometric_annual_return(
            raw_strategy_returns,
            periods_per_year,
        )
    analysis = getattr(result, "factor_analysis", {})
    factor_analysis = None
    layered_equity = pd.DataFrame()
    if req.analysis_level in {"core", "full"}:
        layered_equity = analysis.get("layered_equity", pd.DataFrame())
        ic_series = analysis.get("ic_series", pd.DataFrame())
        cumulative_ic = analysis.get("cumulative_ic", pd.Series(dtype=float))
        rolling_ir = analysis.get("rolling_ir", pd.Series(dtype=float))
        has_layered_groups = len(layered_equity.columns) >= req.groups
        layered_returns = {
            "groups": req.groups,
            "long_short_return": metrics.get("total_return"),
        }
        if has_layered_groups:
            layered_returns.update({
                f"layer{number}": float(layered_equity.iloc[-1, number - 1] - 1)
                for number in range(1, req.groups + 1)
            })
            layered_returns["spread"] = float(
                layered_equity.iloc[-1, 0] - layered_equity.iloc[-1, -1]
            )
        else:
            layered_returns["spread"] = None
        factor_analysis = FactorAnalysis(
            ic_mean=metrics.get("ic"),
            ic_std=metrics.get("ic_std"),
            rank_ic_mean=metrics.get("rank_ic"),
            layered_returns=layered_returns,
            cumulative_series=_layered_equity_to_points(layered_equity),
            definition={
                "ic_type": "pearson",
                "forward_return_days": 1,
                "signal_lag_days": 0,
                "rolling_ir_window": 60,
                "groups": req.groups,
                "analysis_level": req.analysis_level,
                "factor_preprocess": result.meta.get("factor_preprocess", {}),
                "grouping_method": "rank_vectorized",
                "group_order": "Q1_highest_factor_value_QN_lowest_factor_value",
                "curve_first_value": 1.0,
                "group_metric_returns": "signal_to_end_including_entry",
                "benchmark_metric_returns": "entry_to_end_with_initial_zero_return",
                "group_annualization": "geometric_cagr",
                "benchmark_annualization": "geometric_cagr",
                "group_volatility_ddof": 1,
                "benchmark_volatility_ddof": 1,
                "group_max_drawdown": "initial_equity_1_plus_full_group_returns",
                "relative_metric_returns": "full_common_daily_group_benchmark_returns",
                "relative_annual_excess_return": "annualized_cumulative_simple_excess",
                "relative_excess_volatility_ddof": 1,
                "relative_information_ratio": "annual_excess_divided_by_excess_volatility",
                "benchmark_win_rate": "common_daily_group_return_vs_cumulative_benchmark_return",
                **({
                    "industry_return_method": "equal_weight_fixed_capital",
                    "industry_grouping_method": "daily_cross_sectional_equal_weight_fixed_capital",
                } if req.analysis_level == "full" else {}),
            },
            ic_series=_ic_points(ic_series),
            cumulative_ic_series=_value_points(cumulative_ic),
            rolling_ir_series=_rolling_ir_points(rolling_ir),
            industry_equity_curves=_industry_equity_to_response(
                analysis.get("industry_equity", {})
            ),
            industry_group_equity_curves=_industry_group_equity_to_response(
                analysis.get("industry_group_equity", {})
            ),
        )
    benchmark_equity = execution.benchmark_equity
    benchmark_curve = _compute_equity_with_drawdown(benchmark_equity)
    if factor_analysis is not None:
        factor_analysis.quantile_metrics = list(execution.quantile_metrics)
    common_dates = equity.index.intersection(benchmark_equity.index)
    excess_return = None
    if len(common_dates):
        strategy_return = equity.loc[common_dates[-1]] / equity.loc[common_dates[0]] - 1
        benchmark_return = benchmark_equity.loc[common_dates[-1]] / benchmark_equity.loc[common_dates[0]] - 1
        excess_return = float(strategy_return - benchmark_return)

    return FactorBacktestResponse(
        metrics=metrics,
        equity_curve=equity_points,
        drawdowns=drawdowns,
        annual_returns=annual_returns,
        factor_analysis=factor_analysis,
        date_range=DateRange(**date_range_from(equity)),
        final_equity=final_equity,
        benchmark_curve=benchmark_curve,
        excess_return=excess_return,
        meta=FactorBacktestMeta(
            factor=req.factor_name,
            universe=req.universe if universe_snapshot is None else universe_snapshot.asset_id,
            portfolio_type=req.portfolio_type,
            rebalance_days=req.rebalance_days,
            groups=req.groups,
            benchmark=req.benchmark,
            filter_limit_up=req.filter_limit_up,
            filter_suspended=req.filter_suspended,
            filter_status=result.meta.get("filter_status", {}),
            warnings=result.meta.get("warnings", []),
            execution_version=result.meta.get("execution_version", execution.spec.execution_version),
            metric_version=result.meta.get("metric_version", execution.spec.metric_version),
            data_release_id=result.meta.get("data_release_id", execution.data_release_id),
            spec_hash=result.meta.get("spec_hash", execution.spec_hash),
            factor_source_hash=result.meta.get("factor_source_hash", execution.spec.factor_source_hash),
            actual_end=result.meta.get("actual_end", execution.actual_end),
            factor_price_adjustment=result.meta.get("factor_price_adjustment"),
            factor_price_source=result.meta.get("factor_price_source"),
            factor_price_fields=result.meta.get("factor_price_fields", []),
            factor_price_precision=result.meta.get("factor_price_precision"),
            return_price_adjustment=result.meta.get("return_price_adjustment"),
            return_price_source=result.meta.get("return_price_source"),
            return_price_precision=result.meta.get("return_price_precision"),
            timings_seconds={
                **result.meta.get("timings_seconds", {}),
                "api_total": round(time.perf_counter() - started_at, 6),
            },
            universe_asset=_asset_meta(universe_snapshot),
            benchmark_asset=_asset_meta(benchmark_snapshot),
        ),
        error=None,
    )


def _strategy_task_key(req: StrategyBacktestRequest) -> str:
    payload = json.dumps(
        req.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "strategy:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def submit_strategy_backtest(
    req: StrategyBacktestRequest,
    manager: ExperimentManager,
) -> ExperimentHandle[StrategyBacktestResponse]:
    """把策略回测提交给指定的应用级 ``ExperimentManager``。"""
    return manager.submit(
        StrategyExperiment(req),
        key=_strategy_task_key(req),
        lane="interactive",
        metadata={"type": "strategy", "engine_mode": req.engine_mode},
    )


def run_strategy_backtest(
    req: StrategyBacktestRequest,
    *,
    manager: ExperimentManager,
) -> StrategyBacktestResponse:
    """同步等待应用级 Manager 中的策略回测。"""
    return submit_strategy_backtest(req, manager).result()


async def run_strategy_backtest_async(
    req: StrategyBacktestRequest,
    *,
    manager: ExperimentManager,
) -> StrategyBacktestResponse:
    """HTTP 层使用的异步等待门面。"""
    handle = submit_strategy_backtest(req, manager)
    return await asyncio.wrap_future(handle.future)


def _run_event_strategy_backtest(
    req: StrategyBacktestRequest,
    strategy_class,
    strategy_id: str | None,
    strategy_version: str | None,
    code_hash: str | None,
    *,
    data_context=None,
) -> StrategyBacktestResponse:
    """事件策略执行门面。"""
    from app.services.strategy.backtest import _run_event_strategy_backtest as _run

    return _run(
        req,
        strategy_class,
        strategy_id,
        strategy_version,
        code_hash,
        data_context=data_context,
    )
