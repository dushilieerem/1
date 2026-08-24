"""核心：因子代码字符串 -> 回测 -> 序列化结果。

复用 :class:`app.FactorLoader` + :class:`app.ExperimentManager`
+ Native 回测适配器，**不新写回测逻辑**，只把 SDK 调用包成可被
HTTP 路由调用的纯函数。

所有异常（语法错 / 导入错 / 运行错 / 因子名不存在）都会被转换为结构化错误。
内部同步包装函数仍返回 ``BacktestResponse.error``；异步 HTTP 任务路由将其映射为
``status=failed`` 和顶层 ``error``。
"""

from __future__ import annotations

import os
import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pandas as pd
import yaml

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
from app.services.experiment import Experiment, ExperimentContext, FactorExperiment, StrategyExperiment
from app.services.experiment.manager import ExperimentHandle, ExperimentManager


def _builtin_factor_library_index() -> dict[str, dict]:
    """读取因子库索引，作为 API 内置库注册的唯一来源。

    ``FactorLoader`` 仍负责加载库的 Python 实现，但 API 是否允许某个
    ``library_name`` 只由 ``app/assets/factors/index.yaml`` 决定。索引文件
    位于 ``factor_library_dir`` 下，因此测试和部署都可以通过
    ``SVQUANT_FACTOR_DIR`` 切换整套因子资产。
    """
    from app.repositories.catalogs.paths import factor_index_path

    index_path = factor_index_path()
    if not index_path.is_file():
        raise FileNotFoundError(f"因子库索引不存在: {index_path}")

    try:
        payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"因子库索引无法解析: {index_path}") from exc

    libraries = payload.get("libraries") if isinstance(payload, dict) else None
    if not isinstance(libraries, dict):
        raise ValueError(f"因子库索引缺少 libraries 映射: {index_path}")

    invalid = [
        name for name, metadata in libraries.items()
        if not isinstance(name, str) or not name or not isinstance(metadata, dict)
    ]
    if invalid:
        raise ValueError(f"因子库索引包含无效库条目: {invalid}")
    return libraries


def builtin_factor_library_names() -> tuple[str, ...]:
    """返回 ``index.yaml`` 中登记的内置因子库名。"""
    return tuple(sorted(_builtin_factor_library_index()))


def _builtin_factor_library_entry(library_name: str) -> tuple[Path, str, dict]:
    """解析并校验一个 YAML 登记的库，返回目录、模块名和元数据。"""
    from app.repositories.catalogs.paths import factor_library_dir

    libraries = _builtin_factor_library_index()
    metadata = libraries.get(library_name)
    if metadata is None:
        raise ValueError(
            f"不支持的内置因子库 {library_name!r}；可用: "
            f"{list(builtin_factor_library_names())}"
        )

    file_name = metadata.get("file")
    file_path = Path(file_name) if isinstance(file_name, str) else None
    factor_dir = factor_library_dir()
    if (
        file_path is None
        or file_path.name != file_name
        or file_path.suffix != ".py"
        or not (factor_dir / file_path).is_file()
    ):
        raise ValueError(
            f"因子库 {library_name!r} 在 index.yaml 中声明的实现文件无效: "
            f"{file_name!r}"
        )
    return factor_dir, file_path.stem, metadata


def _load_builtin_factor_library(library_name: str):
    """按 ``index.yaml`` 的文件声明加载一个内置因子库。"""
    from app import FactorLoader

    factor_dir, module_name, metadata = _builtin_factor_library_entry(library_name)
    loader = FactorLoader(factor_dir=str(factor_dir))
    library = loader.load(module_name)

    registered_factors = metadata.get("factors")
    if not isinstance(registered_factors, list):
        raise ValueError(
            f"因子库 {library_name!r} 尚未由 factor_catalog 同步完整因子清单"
        )
    registered_names = [
        item.get("name")
        for item in registered_factors
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    actual_names = sorted(loader.factors)
    if len(registered_names) != len(set(registered_names)) or sorted(registered_names) != actual_names:
        missing = sorted(set(actual_names) - set(registered_names))
        extra = sorted(set(registered_names) - set(actual_names))
        raise ValueError(
            f"因子库 {library_name!r} 与 index.yaml 未同步；"
            f"源码新增未登记: {missing}; 索引中不存在: {extra}"
        )
    if metadata.get("factor_count") != len(actual_names):
        raise ValueError(
            f"因子库 {library_name!r} 的 factor_count 与源码不一致；"
            f"索引: {metadata.get('factor_count')}; 源码: {len(actual_names)}"
        )
    expected_class = metadata.get("class")
    if expected_class and type(library).__name__ != expected_class:
        raise ValueError(
            f"因子库 {library_name!r} 的 class 与源码不一致；"
            f"索引: {expected_class}; 源码: {type(library).__name__}"
        )
    return loader, library


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
    from app.repositories.catalogs.paths import backtest_cache_dir
    from app.repositories.results.cache import FileBacktestCache

    return FileBacktestCache(
        backtest_cache_dir(),
        ttl_days=_cache_int_env("SVQUANT_BACKTEST_CACHE_TTL_DAYS", 30),
        max_bytes=_cache_int_env("SVQUANT_BACKTEST_CACHE_MAX_BYTES", 10 * 1024**3),
    )


def _factor_cache_key(req: FactorBacktestRequest, cache) -> str:
    return cache.make_key(
        req.model_dump(mode="json"),
        cache.data_fingerprint(Path(_resolve_data_dir(None))),
    )


def _run_cached_factor_backtest(
    req: FactorBacktestRequest, cache, key: str, *, data_context=None
) -> tuple[FactorBacktestResponse, str]:
    """在线程池中完成缓存复核、文件锁协调和实际因子回测。"""
    try:
        cached = cache.get(key)
        if cached is not None:
            return FactorBacktestResponse.model_validate(cached), "HIT"

        with cache.lock(key) as acquired:
            cached = cache.get(key)
            if cached is not None:
                return FactorBacktestResponse.model_validate(cached), "HIT"
            result = _run_factor_backtest_uncached(req, data_context=data_context)
            if acquired and result.error is None:
                try:
                    cache.set(key, result.model_dump(mode="json"))
                except Exception:  # noqa: BLE001 写缓存失败不重复执行回测
                    return result, "BYPASS"
            return result, "MISS"
    except Exception:  # noqa: BLE001 缓存不可用不得阻断研究回测
        return _run_factor_backtest_uncached(req, data_context=data_context), "BYPASS"


def _factor_task_key(req: FactorBacktestRequest) -> str:
    """生成进程内同请求去重键，不读取行情文件。"""

    payload = json.dumps(
        req.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "factor-request:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run_factor_backtest_job(
    req: FactorBacktestRequest,
    *,
    data_context=None,
) -> tuple[FactorBacktestResponse, str]:
    """在线程池中计算行情指纹、读取缓存并执行因子回测。"""

    if not _cache_enabled():
        return _run_factor_backtest_uncached(req, data_context=data_context), "BYPASS"

    try:
        cache = _factor_cache()
        key = _factor_cache_key(req, cache)
    except Exception:  # noqa: BLE001 缓存不可用不得阻断研究回测
        return _run_factor_backtest_uncached(req, data_context=data_context), "BYPASS"
    return _run_cached_factor_backtest(req, cache, key, data_context=data_context)


class FactorBacktestExperiment(Experiment[tuple[FactorBacktestResponse, str]]):
    """API 因子回测请求的 Experiment 适配器。"""

    def __init__(self, request: FactorBacktestRequest) -> None:
        self.request = request

    def run(self, context: ExperimentContext) -> tuple[FactorBacktestResponse, str]:
        return _run_factor_backtest_job(self.request, data_context=context.market)


def submit_factor_backtest(
    req: FactorBacktestRequest,
    manager: ExperimentManager,
) -> ExperimentHandle[tuple[FactorBacktestResponse, str]]:
    """只创建因子回测任务；缓存扫描和行情读取均在线程池中执行。"""

    return manager.submit(
        FactorBacktestExperiment(req),
        key=_factor_task_key(req),
        lane="interactive",
        metadata={"type": "factor", "cache": "PENDING"},
    )


def _unpack_factor_result(
    handle: ExperimentHandle[tuple[FactorBacktestResponse, str]], response=None
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


def _wrap_factor_code(factor_code: str) -> str:
    """自动补全因子代码：用户只写函数体，系统添加 import 和 class 头。"""
    wrapped = (
        "from app.quantcore import FactorLibrary\n\n"
        "class UserFactorLibrary(FactorLibrary):\n"
        "    author = \"user\"\n\n"
    )
    for line in factor_code.splitlines():
        if line.strip():
            wrapped += f"    {line}\n"
        else:
            wrapped += "\n"
    return wrapped


def _load_factor_from_code(
    factor_code: str, factor_name: str, library_names: list[str] | None = None,
):
    """把因子源码写到临时文件，用 :class:`FactorLoader` 加载，取出指定因子。

    因子对象本身是内存中的活实例，临时文件加载完即可清理。
    因子代码自动补全 FactorLibrary 类头，用户只需写函数体。
    """
    from app import FactorLoader

    full_code = _wrap_factor_code(factor_code)

    tmpdir = tempfile.mkdtemp(prefix="svquant_api_")
    mod_name = f"user_factor_{uuid.uuid4().hex[:8]}"
    factor_file = Path(tmpdir) / f"{mod_name}.py"
    factor_file.write_text(full_code, encoding="utf-8")

    try:
        loader = FactorLoader(factor_dir=str(tmpdir))
        library = loader.load(mod_name)
        _attach_builtin_library_methods(library, library_names or [])
        if factor_name not in loader.factors:
            raise KeyError(
                f"因子 {factor_name!r} 未找到；可用: {list(loader.factors)}"
            )
        return loader.factors[factor_name]
    finally:
        # 清理：弹 sys.modules 与临时目录（FactorLoader 会把 tmpdir 加进 sys.path）
        sys.modules.pop(mod_name, None)
        try:
            sys.path.remove(str(tmpdir))
        except ValueError:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


def _attach_builtin_library_methods(target_library, library_names: list[str]) -> None:
    """将内置库因子作为用户组合因子的方法依赖注入临时库。"""
    from app.quantcore.factor.base import library_factors

    # 因子库方法在 ``_MethodFactor.compute`` 中会被复制到每个 Worker 的
    # library 实例。把依赖方法挂在实例字典上会绕过 Python 的 descriptor
    # 绑定，复制后的方法仍然闭包指向原始实例，导致并发时读取错误的
    # ``_panel``。挂到临时库的动态 class 上，让每次调用都绑定当前副本。
    library_type = type(target_library)
    for library_name in library_names:
        _loader, source_library = _load_builtin_factor_library(library_name)
        for factor_name, factor in library_factors(source_library).items():
            if hasattr(target_library, factor_name):
                raise ValueError(f"内置因子 {factor_name!r} 与自定义因子方法重名")

            def builtin_method(self, _factor=factor):
                return _factor.compute(self._panel)

            setattr(library_type, factor_name, builtin_method)


def _load_factor_from_builtin_library(library_name: str, factor_name: str):
    """从登记的内置因子库加载指定因子，不执行前端提交的源码。"""
    loader, _library = _load_builtin_factor_library(library_name)
    if factor_name not in loader.factors:
        raise KeyError(
            f"因子 {factor_name!r} 不在内置库 {library_name!r} 中；"
            f"可用: {list(loader.factors)}"
        )
    return loader.factors[factor_name]


def _build_config(commission_rate, slippage_rate, stamp_tax=None,
                  rebalance_days=None, groups=None, long_short=None,
                  analysis_level: str = "core", winsorize: int = 0,
                  standardize: int = 0):
    """由参数构建 :class:`ConfigManager`（不设 output_path -> 不落盘）。"""
    from app import ConfigManager

    cfg = ConfigManager()
    cfg.set("data_dir", _resolve_data_dir(None))
    if rebalance_days is not None:
        cfg.set("rebalance_days", rebalance_days)
    if groups is not None:
        cfg.set("groups", groups)
        cfg.set("n_groups", groups)
        cfg.set("n_layered_groups", groups)
    cfg.set("factor_preprocess.winsorize", winsorize)
    cfg.set("factor_preprocess.standardize", standardize)
    if long_short is not None:
        cfg.set("long_short", long_short)
    if stamp_tax is not None:
        cfg.set("stamp_tax", stamp_tax)
    cfg.set("backtest.engine", "native")
    cfg.set("backtest.initial_capital", 1_000_000.0)
    cfg.set("backtest.commission_rate", commission_rate)
    cfg.set("backtest.slippage_rate", slippage_rate)
    cfg.set("periods_per_year", 252)
    cfg.set("compute_backend", "python")
    cfg.set("factor_analysis.level", analysis_level)
    return cfg


def _run_factor_backtest_uncached(
    req: FactorBacktestRequest,
    *,
    data_context=None,
) -> FactorBacktestResponse:
    """因子回测：因子代码 + 参数 -> 指标 + 净值 + 因子分析。"""
    started_at = time.perf_counter()
    try:
        if data_context is None:
            raise RuntimeError("FactorExperiment 必须由 ExperimentManager 提供行情上下文")
        data_engine = data_context.data_engine
        universe, universe_snapshot, benchmark_snapshot = _resolve_research_assets(
            req,
            data_engine=data_engine,
        )

        factor = (
            _load_factor_from_code(req.factor_code, req.factor_name, req.library_names)
            if req.factor_code is not None
            else _load_factor_from_builtin_library(req.library_names[0], req.factor_name)
        )

        # 组合方式映射
        long_short = req.portfolio_type == "long_short"

        cfg = _build_config(
            commission_rate=req.commission_rate,
            slippage_rate=req.slippage_rate,
            stamp_tax=req.stamp_tax,
            rebalance_days=req.rebalance_days,
            groups=req.groups,
            long_short=long_short,
            analysis_level=req.analysis_level,
            winsorize=req.winsorize,
            standardize=req.standardize,
        )
        exp = FactorExperiment(
            factor=factor,
            universe=universe,
            start_date=req.start,
            end_date=req.end,
            config=cfg,
        )
        if data_context is None:
            raise RuntimeError("FactorExperiment 必须由 ExperimentManager 提供行情上下文")
        result = exp.run(ExperimentContext(data_context))  # ResultManager
        if universe_snapshot is not None or benchmark_snapshot is not None:
            result.meta["research_assets"] = {
                **({"universe": _persisted_asset(universe_snapshot)} if universe_snapshot else {}),
                **({"benchmark": _persisted_asset(benchmark_snapshot)} if benchmark_snapshot else {}),
            }
    except Exception as exc:  # noqa: BLE001  任何错都回前端
        return FactorBacktestResponse(
            error=f"{type(exc).__name__}: {exc}",
            meta=None,
        )

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
            int(cfg.get("periods_per_year", 252)),
        )
    analysis = getattr(result, "factor_analysis", {})
    factor_analysis = None
    layered_equity = pd.DataFrame()
    layered_return_frame = pd.DataFrame()
    if req.analysis_level in {"core", "full"}:
        layered_equity = analysis.get("layered_equity", pd.DataFrame())
        layered_return_frame = analysis.get("layered_returns", pd.DataFrame())
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
                "grouping_method": "pd.qcut_raw_value",
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
    try:
        benchmark_equity = _benchmark_equity(
            req.benchmark,
            benchmark_snapshot,
            equity.index,
            data_engine=data_engine,
        )
    except Exception as exc:  # noqa: BLE001
        return FactorBacktestResponse(error=f"{type(exc).__name__}: {exc}", meta=None)
    benchmark_curve = _compute_equity_with_drawdown(benchmark_equity)
    if factor_analysis is not None:
        relative_benchmark_returns = (
            benchmark_equity
            .pct_change(fill_method=None)
            .reindex(layered_return_frame.index)
        )
        if not relative_benchmark_returns.empty:
            first_common_date = layered_return_frame.index[0]
            if pd.isna(relative_benchmark_returns.loc[first_common_date]):
                relative_benchmark_returns.loc[first_common_date] = 0.0
        factor_analysis.quantile_metrics = _compute_quantile_metrics(
            layered_equity,
            benchmark_equity,
            periods_per_year=int(cfg.get("periods_per_year", 252)),
            layered_returns=layered_return_frame,
            relative_benchmark_returns=relative_benchmark_returns,
        )
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
