"""全量内置因子批量回测业务的编排与指标摘要。"""

from __future__ import annotations

import hashlib
import inspect
import json
import time
from concurrent.futures import FIRST_COMPLETED, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.services.factor.backtest_support import (
    _load_benchmark_equity,
    _resolve_current_data_dir,
)
from app.services.factor.metrics import _compute_quantile_metrics
from app.services.factor.runner import (
    _build_config,
    _builtin_factor_library_index,
    _load_builtin_factor_library,
)
from app.services.experiment import Experiment, ExperimentContext, FactorExperiment
from app.repositories.factor_backtest import FactorBacktestRepository
from app.services.experiment.manager import (
    ExperimentManager,
    ExperimentQueueFullError,
)


METRIC_VERSION = "factor-scorecard-v1"
_REQUIRED_BENCHMARK_FILE = "index_price_000300.SH.parquet"


class FactorBatchSkip(RuntimeError):
    """表示当前因子不可形成可用指标，但不应使批次失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FactorCatalogItem:
    library_name: str
    factor_name: str
    source_hash: str
    factor: Any | None = None
    load_error: str | None = None


@dataclass(frozen=True)
class FactorBacktestBatchProfile:
    as_of_date: str
    lookback_years: int = 10
    universe: str = "CSI_ALL"
    benchmark: str = "CSI300"
    portfolio_type: str = "long_only"
    groups: int = 5
    rebalance_days: int = 1
    analysis_level: str = "core"
    filter_limit_up: bool = True
    filter_suspended: bool = True
    commission_rate: float = 0.0
    stamp_tax: float = 0.0
    slippage_rate: float = 0.0
    winsorize: int = 0
    standardize: int = 0

    def __post_init__(self) -> None:
        timestamp = pd.Timestamp(self.as_of_date)
        if pd.isna(timestamp):
            raise ValueError(f"无效 as_of_date: {self.as_of_date!r}")
        if self.lookback_years < 1:
            raise ValueError("lookback_years 必须大于 0")
        object.__setattr__(self, "as_of_date", timestamp.date().isoformat())
        if self.benchmark != "CSI300":
            raise ValueError("因子批量回测当前只支持 CSI300 基准")
        if self.universe != "CSI_ALL":
            raise ValueError("因子批量回测当前只支持 CSI_ALL 股票池")
        if self.portfolio_type != "long_only":
            raise ValueError("因子批量回测当前只支持纯多头")
        if self.groups != 5 or self.rebalance_days != 1:
            raise ValueError("因子批量回测固定为 5 组、每日调仓")
        if self.analysis_level != "core":
            raise ValueError("因子批量回测固定使用 core 分析")
        if not self.filter_limit_up or not self.filter_suspended:
            raise ValueError("因子批量回测固定开启涨停和停牌过滤")

    @property
    def window_start(self) -> str:
        return (pd.Timestamp(self.as_of_date) - pd.DateOffset(years=self.lookback_years)).date().isoformat()

    @property
    def window_end(self) -> str:
        return self.as_of_date

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date,
            "lookback_years": self.lookback_years,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "universe": self.universe,
            "benchmark": self.benchmark,
            "portfolio_type": self.portfolio_type,
            "groups": self.groups,
            "rebalance_days": self.rebalance_days,
            "analysis_level": self.analysis_level,
            "filter_limit_up": self.filter_limit_up,
            "filter_suspended": self.filter_suspended,
            "commission_rate": self.commission_rate,
            "stamp_tax": self.stamp_tax,
            "slippage_rate": self.slippage_rate,
            "winsorize": self.winsorize,
            "standardize": self.standardize,
        }


@dataclass(frozen=True)
class FactorOutcome:
    status: str
    retry_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    actual_start: str | None = None
    actual_end: str | None = None
    observation_days: int | None = None
    sample_quality: str | None = None
    elapsed_seconds: float | None = None
    quantile_metrics: tuple[dict[str, Any], ...] = ()
    predictive_metrics: dict[str, Any] | None = None


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _catalog_items() -> tuple[tuple[str, ...], str, list[FactorCatalogItem]]:
    """读取索引并尽量把库加载错误降级到受影响因子。"""

    from app.repositories.catalogs.paths import factor_index_path, factor_library_dir

    index_path = factor_index_path()
    libraries = _builtin_factor_library_index()
    index_text = index_path.read_text(encoding="utf-8")
    items: list[FactorCatalogItem] = []
    library_names = tuple(sorted(libraries))
    for library_name in library_names:
        metadata = libraries[library_name]
        declared = metadata.get("factors")
        if not isinstance(declared, list):
            raise ValueError(f"因子库 {library_name!r} 尚未登记完整因子清单")
        names = sorted(
            item["name"]
            for item in declared
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        )
        file_name = metadata.get("file")
        source_path = factor_library_dir() / str(file_name)
        source_hash = _source_hash(source_path) if source_path.is_file() else "missing"
        try:
            loader, _library = _load_builtin_factor_library(library_name)
            actual = sorted(loader.factors)
            if actual != names:
                raise ValueError(
                    f"索引因子清单与源码不一致: declared={len(names)}, actual={len(actual)}"
                )
            for name in names:
                items.append(
                    FactorCatalogItem(
                        library_name=library_name,
                        factor_name=name,
                        source_hash=source_hash,
                        factor=loader.factors[name],
                    )
                )
        except Exception as exc:  # noqa: BLE001 - 单库错误隔离到因子行
            message = f"{type(exc).__name__}: {exc}"
            for name in names:
                items.append(
                    FactorCatalogItem(
                        library_name=library_name,
                        factor_name=name,
                        source_hash=source_hash,
                        load_error=message,
                    )
                )
    # 索引未变但源码变更时也必须生成新批次键；否则会错误复用旧评分卡。
    catalog_version = _stable_hash({
        "index": index_text,
        "metric_version": METRIC_VERSION,
        "sources": [
            {
                "library_name": item.library_name,
                "factor_source_hash": item.source_hash,
            }
            for item in items
        ],
    })
    return library_names, catalog_version, items


def _preflight(
    profile: FactorBacktestBatchProfile,
    item_count: int,
    *,
    data_context=None,
) -> dict[str, Any]:
    data_dir = (
        data_context.data_dir
        if data_context is not None
        else _resolve_current_data_dir()
    )
    if not data_dir.is_dir():
        raise FileNotFoundError(f"当前行情目录不存在: {data_dir}")
    benchmark_path = data_dir / "benchmark" / _REQUIRED_BENCHMARK_FILE
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"CSI300 基准文件不存在: {benchmark_path}")
    if data_context is not None:
        benchmark_frame = data_context.data_engine.get_index("CSI300")
    else:
        benchmark_frame = pd.read_parquet(benchmark_path)
    benchmark_index = pd.to_datetime(benchmark_frame.index).normalize()
    as_of = pd.Timestamp(profile.as_of_date).normalize()
    if as_of not in benchmark_index:
        raise ValueError(f"as_of_date 不是 CSI300 基准中的交易日: {profile.as_of_date}")
    in_window = benchmark_index[
        (benchmark_index >= pd.Timestamp(profile.window_start))
        & (benchmark_index <= as_of)
    ]
    if len(in_window) == 0:
        raise ValueError(
            f"CSI300 基准与评估区间没有重叠数据: {profile.window_start}~{profile.window_end}"
        )
    try:
        if data_context is not None:
            provider = data_context.provider
        else:
            from app.quantcore import FieldParquetProvider

            provider = FieldParquetProvider(str(data_dir))
        symbols = provider.get_universe(profile.universe)
        close = provider.get_panels(
            profile.window_start,
            profile.window_end,
            fields=["close"],
        )["close"]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"全 A 股票池不可用: {exc}") from exc
    if not symbols:
        raise RuntimeError("全 A 股票池为空")
    if close.empty or pd.Timestamp(profile.as_of_date) not in pd.to_datetime(close.index):
        raise ValueError(f"行情 close 与 as_of_date 不重叠: {profile.as_of_date}")
    return {
        "data_dir": str(data_dir),
        "benchmark": str(benchmark_path),
        "universe_count": len(symbols),
        "factor_count": item_count,
        "window_start": profile.window_start,
        "window_end": profile.window_end,
    }


def _build_factor_config(profile: FactorBacktestBatchProfile):
    config = _build_config(
        commission_rate=profile.commission_rate,
        slippage_rate=profile.slippage_rate,
        stamp_tax=profile.stamp_tax,
        rebalance_days=profile.rebalance_days,
        groups=profile.groups,
        long_short=False,
        analysis_level=profile.analysis_level,
        winsorize=profile.winsorize,
        standardize=profile.standardize,
    )
    config.set("factor_batch.filters_enabled", True)
    config.set("factor_batch.strict_as_of", True)
    config.set("filter_limit_up", profile.filter_limit_up)
    config.set("filter_suspended", profile.filter_suspended)
    return config


def _as_metric_dict(metric: Any) -> dict[str, Any]:
    if hasattr(metric, "model_dump"):
        return metric.model_dump(mode="json")
    return dict(metric)


def _call_with_optional_keyword(func, args: tuple[Any, ...], name: str, value: Any):
    """兼容旧测试/扩展替身不接收新增上下文关键字的调用。"""

    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if name in parameters or accepts_kwargs:
        return func(*args, **{name: value})
    return func(*args)


def _catalog_error_status(message: str) -> tuple[str, str]:
    """区分索引中声明但源码不存在的因子与整库加载错误。"""

    if "索引中不存在" in message or "因子不存在" in message:
        return "skipped", "factor_not_found"
    return "failed", "catalog_error"


def _run_factor_once(
    profile: FactorBacktestBatchProfile,
    item: FactorCatalogItem,
    *,
    data_context=None,
) -> FactorOutcome:
    started = time.perf_counter()
    if item.load_error:
        status, error_code = _catalog_error_status(item.load_error)
        return FactorOutcome(
            status=status,
            error_code=error_code,
            error_message=item.load_error,
            elapsed_seconds=time.perf_counter() - started,
        )
    if item.factor is None:
        return FactorOutcome(
            status="failed",
            error_code="factor_unavailable",
            error_message="因子未加载",
            elapsed_seconds=time.perf_counter() - started,
        )

    if data_context is None:
        raise RuntimeError("FactorBacktestBatchExperiment 必须由 ExperimentManager 提供行情上下文")
    config = _build_factor_config(profile)
    experiment = FactorExperiment(
        factor=item.factor,
        universe=profile.universe,
        start_date=profile.window_start,
        end_date=profile.window_end,
        config=config,
    )
    result = experiment.run(ExperimentContext(data_context))
    equity = result.equity_curve
    if equity is None or equity.empty:
        raise FactorBatchSkip("empty_equity", "回测未生成有效净值")
    analysis = getattr(result, "factor_analysis", {}) or {}
    layered_equity = analysis.get("layered_equity")
    layered_returns = analysis.get("layered_returns")
    if layered_equity is None or getattr(layered_equity, "empty", True):
        raise FactorBatchSkip("empty_quantile_metrics", "未生成分组净值")
    if data_context is None:
        benchmark = _load_benchmark_equity(profile.benchmark, equity.index)
    else:
        benchmark = _load_benchmark_equity(
            profile.benchmark,
            equity.index,
            data_engine=data_context.data_engine,
        )
    relative_benchmark_returns = benchmark.pct_change(fill_method=None)
    if not layered_returns.empty:
        relative_benchmark_returns = relative_benchmark_returns.reindex(layered_returns.index)
        first_common_date = layered_returns.index[0]
        if pd.isna(relative_benchmark_returns.loc[first_common_date]):
            relative_benchmark_returns.loc[first_common_date] = 0.0
    quantile_metrics = tuple(
        _as_metric_dict(metric)
        for metric in _compute_quantile_metrics(
            layered_equity,
            benchmark,
            periods_per_year=252,
            layered_returns=layered_returns,
            relative_benchmark_returns=relative_benchmark_returns,
        )
    )
    expected_quantiles = ("Q1", "Q2", "Q3", "Q4", "Q5", "benchmark")
    metric_by_name = {str(row.get("quantile")): row for row in quantile_metrics}
    if any(name not in metric_by_name for name in expected_quantiles):
        raise FactorBatchSkip("incomplete_quantile_metrics", "分组指标行数不足")
    if not any(
        metric_by_name[name].get("annual_return") is not None
        for name in expected_quantiles
    ):
        raise FactorBatchSkip("invalid_quantile_metrics", "分组指标没有有效年化收益")
    quantile_metrics = tuple(metric_by_name[name] for name in expected_quantiles)

    actual_start = pd.Timestamp(equity.index.min()).date().isoformat()
    actual_end = pd.Timestamp(equity.index.max()).date().isoformat()
    requested_days = (pd.Timestamp(profile.window_end) - pd.Timestamp(profile.window_start)).days
    actual_days = max(0, (pd.Timestamp(actual_end) - pd.Timestamp(actual_start)).days)
    sample_quality = "short_history" if actual_days < requested_days else "complete"
    predictive = analysis.get("predictive_summary") or {}
    return FactorOutcome(
        status="succeeded",
        actual_start=actual_start,
        actual_end=actual_end,
        observation_days=int(len(equity)),
        sample_quality=sample_quality,
        elapsed_seconds=time.perf_counter() - started,
        quantile_metrics=quantile_metrics,
        predictive_metrics={
            "ic_mean": predictive.get("ic_mean"),
            "rank_ic_mean": predictive.get("rank_ic_mean"),
            "ic_ir": predictive.get("ic_ir"),
        },
    )


class FactorBacktestBatchExperiment(Experiment[FactorOutcome]):
    """批量回测窗口中的单因子业务实验。"""

    def __init__(self, profile: FactorBacktestBatchProfile, item: FactorCatalogItem) -> None:
        self.profile = profile
        self.item = item

    def run(self, context: ExperimentContext) -> FactorOutcome:
        return _run_factor_with_retry(
            self.profile,
            self.item,
            data_context=context.market,
        )


def _should_skip(exc: BaseException) -> bool:
    if isinstance(exc, (FileNotFoundError, KeyError, FactorBatchSkip)):
        return True
    text = str(exc)
    return any(token in text for token in ("缺少", "没有可用", "为空", "不存在", "overlap", "missing"))


def _run_factor_with_retry(
    profile: FactorBacktestBatchProfile,
    item: FactorCatalogItem,
    *,
    data_context=None,
) -> FactorOutcome:
    for attempt in range(2):
        attempt_started = time.perf_counter()
        try:
            outcome = _call_with_optional_keyword(
                _run_factor_once,
                (profile, item),
                "data_context",
                data_context,
            )
            return FactorOutcome(**{
                **outcome.__dict__,
                "retry_count": attempt,
                "elapsed_seconds": outcome.elapsed_seconds
                if outcome.elapsed_seconds is not None
                else time.perf_counter() - attempt_started,
            })
        except FactorBatchSkip as exc:
            return FactorOutcome(
                status="skipped",
                retry_count=attempt,
                error_code=exc.code,
                error_message=str(exc),
                elapsed_seconds=time.perf_counter() - attempt_started,
            )
        except (TypeError, ValueError) as exc:
            # 参数错误、因子返回类型不兼容和分组输入不满足约束均不重试。
            return FactorOutcome(
                status="skipped",
                retry_count=attempt,
                error_code="factor_incompatible",
                error_message=f"{type(exc).__name__}: {exc}",
                elapsed_seconds=time.perf_counter() - attempt_started,
            )
        except Exception as exc:  # noqa: BLE001 - 单因子隔离
            if _should_skip(exc):
                return FactorOutcome(
                    status="skipped",
                    retry_count=attempt,
                    error_code="data_unavailable",
                    error_message=f"{type(exc).__name__}: {exc}",
                    elapsed_seconds=time.perf_counter() - attempt_started,
                )
            if attempt == 1:
                return FactorOutcome(
                    status="failed",
                    retry_count=attempt,
                    error_code="runtime_error",
                    error_message=f"{type(exc).__name__}: {exc}",
                    elapsed_seconds=time.perf_counter() - attempt_started,
                )
    return FactorOutcome(status="failed", error_code="unknown", error_message="未知因子错误")


def run_factor_backtest_batch(
    profile: FactorBacktestBatchProfile,
    *,
    manager: ExperimentManager,
    db_path: str | Path | None = None,
    batch_window: int = 2,
    force_retry: bool = False,
    dry_run: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """执行或续跑一个因子批次，并返回批次摘要。"""

    if batch_window != 2:
        raise ValueError("因子批量回测窗口固定为 2")
    repository: FactorBacktestRepository | None = None
    profile_payload = profile.to_dict()
    profile_hash = _stable_hash(profile_payload)

    def get_repository() -> FactorBacktestRepository:
        nonlocal repository
        if repository is None:
            repository = FactorBacktestRepository(db_path)
        return repository

    def record_infrastructure_failure(exc: BaseException) -> dict[str, Any]:
        """把索引/行情预检错误写成可查询的失败批次。"""

        catalog_version = "unavailable"
        batch_key = _stable_hash({
            "as_of_date": profile.as_of_date,
            "profile_hash": profile_hash,
            "catalog_version": catalog_version,
            "metric_version": METRIC_VERSION,
        })
        result_repository = get_repository()
        existing = result_repository.get_batch_by_key(batch_key)
        if existing and not force_retry:
            return existing
        batch = result_repository.create_batch(
            batch_key=batch_key if not force_retry else f"{batch_key}:{time.time_ns()}",
            as_of_date=profile.as_of_date,
            window_start=profile.window_start,
            window_end=profile.window_end,
            profile=profile_payload,
            profile_hash=profile_hash,
            catalog_version=catalog_version,
            metric_version=METRIC_VERSION,
            total_count=0,
            supersedes_batch_id=existing["id"] if existing else None,
        )
        result_repository.mark_batch_failed(
            batch["id"],
            error_code="preflight_error",
            error_message=f"{type(exc).__name__}: {exc}",
        )
        return result_repository.get_batch(batch["id"]) or batch

    try:
        _libraries, catalog_version, items = _catalog_items()
        if not items:
            raise ValueError("因子索引未登记任何可运行因子")
    except Exception as exc:  # noqa: BLE001 - 索引失败才终止批次
        if dry_run:
            raise
        return record_infrastructure_failure(exc)

    batch_key = _stable_hash({
        "as_of_date": profile.as_of_date,
        "profile_hash": profile_hash,
        "catalog_version": catalog_version,
        "metric_version": METRIC_VERSION,
    })
    existing = get_repository().get_batch_by_key(batch_key) if not dry_run else None
    # 已完成批次无需重新扫描行情；这也是任务计划重复触发时的快速路径。
    if existing and not force_retry and existing["status"] == "completed" and not dry_run:
        return existing

    manager.start()
    try:
        try:
            data_context = manager.get_data_context()
            preflight = _call_with_optional_keyword(
                _preflight,
                (profile, len(items)),
                "data_context",
                data_context,
            )
        except Exception as exc:  # noqa: BLE001 - 基础设施失败才终止批次
            if dry_run:
                raise
            return record_infrastructure_failure(exc)
        if dry_run:
            return {
                "status": "dry_run",
                "profile": profile.to_dict(),
                "catalog_version": catalog_version,
                "preflight": preflight,
            }

        repository = get_repository()
        supersedes = None
        if existing and not force_retry:
            if existing["status"] == "completed":
                return existing
            batch = existing
        else:
            supersedes = existing["id"] if existing else None
            batch = repository.create_batch(
                batch_key=batch_key if not force_retry else f"{batch_key}:{time.time_ns()}",
                as_of_date=profile.as_of_date,
                window_start=profile.window_start,
                window_end=profile.window_end,
                profile=profile_payload,
                profile_hash=profile_hash,
                catalog_version=catalog_version,
                metric_version=METRIC_VERSION,
                total_count=len(items),
                supersedes_batch_id=supersedes,
            )

        batch_id = str(batch["id"])
        repository.mark_batch_running(batch_id)
        factor_runs = {
            (item.library_name, item.factor_name): repository.ensure_factor_run(
                batch_id=batch_id,
                library_name=item.library_name,
                factor_name=item.factor_name,
                factor_source_hash=item.source_hash,
            )
            for item in items
        }
        completed_count = sum(
            row["status"] in {"succeeded", "failed", "skipped"}
            for row in factor_runs.values()
        )

        def emit_progress() -> None:
            if progress_callback is not None:
                progress_callback(completed_count, len(items))

        emit_progress()

        pending: dict[Any, tuple[FactorCatalogItem, str]] = {}
        iterator = iter(items)
        while True:
            while len(pending) < batch_window:
                try:
                    item = next(iterator)
                except StopIteration:
                    break
                row = factor_runs[(item.library_name, item.factor_name)]
                if row["status"] in {"succeeded", "failed", "skipped"}:
                    continue
                factor_run_id = str(row["id"])
                if item.load_error:
                    status, error_code = _catalog_error_status(item.load_error)
                    repository.record_factor(
                        factor_run_id,
                        status=status,
                        error_code=error_code,
                        error_message=item.load_error,
                    )
                    completed_count += 1
                    emit_progress()
                    continue
                # Manager 是普通 FIFO 且有界。批量业务不扩大 Manager 的容量，
                # 只在容量暂时被交互任务占满时等待可提交；等待发生在协调器线程，
                # 不会占用回测 worker。
                while True:
                    try:
                        handle = manager.submit(
                            FactorBacktestBatchExperiment(profile, item),
                            lane="batch",
                            metadata={"type": "factor_backtest_batch", "factor": item.factor_name},
                        )
                        break
                    except ExperimentQueueFullError:
                        time.sleep(0.05)
                repository.mark_factor_running(factor_run_id)
                pending[handle.future] = (item, factor_run_id)
            if not pending:
                break
            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            # 即使两个 future 同时完成，也一次只消费一个结果并补一个任务。
            # 这样“一个批量因子进入终态，才提交下一个”在业务代码层面是
            # 明确且可测试的，而不是依赖 wait 返回集合的偶然顺序。
            future = next(iter(done))
            item, factor_run_id = pending.pop(future)
            try:
                outcome: FactorOutcome = future.result()
            except Exception as exc:  # pragma: no cover - defensive manager guard
                outcome = FactorOutcome(
                    status="failed",
                    error_code="manager_error",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            repository.record_factor(
                factor_run_id,
                status=outcome.status,
                retry_count=outcome.retry_count,
                error_code=outcome.error_code,
                error_message=outcome.error_message,
                actual_start=outcome.actual_start,
                actual_end=outcome.actual_end,
                observation_days=outcome.observation_days,
                sample_quality=outcome.sample_quality,
                elapsed_seconds=outcome.elapsed_seconds,
                quantile_metrics=outcome.quantile_metrics,
                predictive_metrics=outcome.predictive_metrics,
            )
            completed_count += 1
            emit_progress()
            repository.refresh_batch_counts(batch_id)
    finally:
        # Manager 属于 FastAPI lifespan；批量业务不得关闭全局行情运行时或 worker。
        pass

    return repository.refresh_batch_counts(batch_id, final=True)


class FactorBacktestBatchCoordinator:
    """因子批量回测业务用例的异步协调器。

    ``batch_window`` 固定为 2：协调器只向 Manager 提交两个尚未完成的
    ``FactorBacktestBatchExperiment``，任意一个进入终态后才补充一个新的因子。
    """

    batch_window = 2

    def __init__(
        self,
        manager: ExperimentManager,
        *,
        db_path: str | Path | None = None,
    ) -> None:
        self.manager = manager
        self.db_path = db_path

    def run_sync(
        self,
        profile: FactorBacktestBatchProfile,
        *,
        force_retry: bool = False,
        dry_run: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        return run_factor_backtest_batch(
            profile,
            manager=self.manager,
            db_path=self.db_path,
            batch_window=self.batch_window,
            force_retry=force_retry,
            dry_run=dry_run,
            progress_callback=progress_callback,
        )

__all__ = [
    "FactorBacktestBatchProfile",
    "FactorBacktestBatchExperiment",
    "FactorBacktestBatchCoordinator",
    "FactorBatchSkip",
    "FactorCatalogItem",
    "FactorOutcome",
    "METRIC_VERSION",
    "run_factor_backtest_batch",
]
