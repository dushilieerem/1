"""全量内置因子批量回测业务的编排与指标摘要。"""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import FIRST_COMPLETED, wait
from app.models.factor_batch import FactorCatalogItem, FactorBacktestBatchProfile, FactorOutcome
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.services.factor.backtest_support import _benchmark_path, _resolve_current_data_dir
from app.services.factor.errors import (
    FactorBacktestDataError,
    FactorBacktestEmptyResult,
    FactorBacktestParameterError,
)
from app.services.factor.experiment import FactorBacktestExperiment
from app.models.factor_backtest import FactorBacktestResult, FactorBacktestSpec
from app.services.factor.sqlite_loader import SQLiteFactorRepository
from app.services.factor.runner import (
    _run_cached_standard_factor_backtest,
)
from app.database.factor_backtest import FactorBacktestRepository
from app.services.experiment.manager import ExperimentManager, ExperimentQueueFullError


METRIC_VERSION = "factor-scorecard-v3"
EXECUTION_VERSION = "factor-execution-v5"


class FactorBatchSkip(RuntimeError):
    """表示当前因子不可形成可用指标，但不应使批次失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code








def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _catalog_items() -> tuple[tuple[str, ...], str, list[FactorCatalogItem]]:
    """读取 SQLite 因子目录并尽量把单因子错误隔离。"""

    repository = SQLiteFactorRepository()
    libraries = repository.list_libraries()
    items: list[FactorCatalogItem] = []
    library_names = tuple(library.library_name for library in libraries)
    for library in libraries:
        try:
            records = repository.list_factors(
                library.library_name,
                validate_code=False,
            )
        except Exception as exc:  # noqa: BLE001 - 单库错误隔离到因子行
            raise ValueError(
                f"SQLite 因子库 {library.library_name!r} 无法读取: {exc}"
            ) from exc
        for record in records:
            source_hash = "missing"
            load_error = None
            try:
                source_hash = repository.source_hash(record)
            except Exception as exc:  # noqa: BLE001 - 仍保留目录项供报告定位
                load_error = f"{type(exc).__name__}: {exc}"
            items.append(
                FactorCatalogItem(
                    library_name=record.library_name,
                    # sv_id 是 SQLite 表定义的稳定主键，作为批量与历史查询键。
                    factor_name=record.sv_id,
                    source_hash=source_hash,
                    load_error=load_error,
                )
            )

    # 数据库或公共工具源码发生变化时必须生成新批次键，避免错误复用旧评分卡。
    catalog_version = _stable_hash({
        "database": repository.catalog_signature(),
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
    benchmark_path = _benchmark_path(data_dir, "CSI300")
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"CSI300 基准文件不存在: {benchmark_path}")
    if data_context is not None:
        benchmark_frame = data_context.get_index("CSI300")
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
            from app.database.data.providers.field_parquet_provider import FieldParquetProvider

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


def _catalog_error_status(message: str) -> tuple[str, str]:
    """区分目录中声明但源码不存在的因子与单因子加载错误。"""

    if "索引中不存在" in message or "因子不存在" in message:
        return "skipped", "factor_not_found"
    return "failed", "catalog_error"


def _factor_spec(
    profile: FactorBacktestBatchProfile,
    item: FactorCatalogItem,
) -> FactorBacktestSpec:
    """把目录项和批量 profile 转成统一计算规格。"""

    return FactorBacktestSpec(
        factor_name=item.factor_name,
        factor_source_hash=item.source_hash,
        library_names=(item.library_name,),
        universe=profile.universe,
        start=profile.window_start,
        end=profile.window_end,
        benchmark=profile.benchmark,
        portfolio_type=profile.portfolio_type,
        rebalance_days=profile.rebalance_days,
        groups=profile.groups,
        commission_rate=profile.commission_rate,
        stamp_tax=profile.stamp_tax,
        slippage_rate=profile.slippage_rate,
        filter_limit_up=profile.filter_limit_up,
        filter_suspended=profile.filter_suspended,
        filters_enabled=bool(profile.filter_limit_up or profile.filter_suspended),
        winsorize=profile.winsorize,
        standardize=profile.standardize,
        analysis_level=profile.analysis_level,
        strict_as_of=True,
        metric_version=METRIC_VERSION,
    )


def _as_metric_dict(metric: Any) -> dict[str, Any]:
    if hasattr(metric, "model_dump"):
        return metric.model_dump(mode="json")
    return dict(metric)


def _outcome_from_result(
    profile: FactorBacktestBatchProfile,
    execution: FactorBacktestResult,
    *,
    started: float,
    retry_count: int = 0,
) -> FactorOutcome:
    """把统一标准结果投影为 SQLite 的批量标量行。"""

    equity = execution.equity_curve
    if equity is None or equity.empty:
        raise FactorBacktestEmptyResult("回测未生成有效净值")
    quantile_metrics = tuple(_as_metric_dict(metric) for metric in execution.quantile_metrics)
    expected_quantiles = tuple(
        [f"Q{number}" for number in range(1, profile.groups + 1)] + ["benchmark"]
    )
    metric_by_name = {str(row.get("quantile")): row for row in quantile_metrics}
    if any(name not in metric_by_name for name in expected_quantiles):
        raise FactorBacktestEmptyResult("未生成完整分组指标")
    if not any(
        metric_by_name[name].get("annual_return") is not None
        for name in expected_quantiles
    ):
        raise FactorBacktestEmptyResult("分组指标没有有效年化收益")
    quantile_metrics = tuple(metric_by_name[name] for name in expected_quantiles)

    actual_start = pd.Timestamp(equity.index.min()).date().isoformat()
    actual_end = pd.Timestamp(equity.index.max()).date().isoformat()
    requested_days = (pd.Timestamp(profile.window_end) - pd.Timestamp(profile.window_start)).days
    actual_days = max(0, (pd.Timestamp(actual_end) - pd.Timestamp(actual_start)).days)
    predictive = dict(execution.predictive_metrics or {})
    warnings = tuple(
        str(item)
        for item in (getattr(getattr(execution, "result_manager", None), "meta", {}) or {}).get(
            "warnings", []
        )
    )
    return FactorOutcome(
        status="succeeded",
        retry_count=retry_count,
        actual_start=actual_start,
        actual_end=actual_end,
        observation_days=int(len(equity)),
        sample_quality="short_history" if actual_days < requested_days else "complete",
        elapsed_seconds=time.perf_counter() - started,
        quantile_metrics=quantile_metrics,
        predictive_metrics={
            "ic_mean": predictive.get("ic_mean"),
            "rank_ic_mean": predictive.get("rank_ic_mean"),
            "ic_ir": predictive.get("ic_ir"),
        },
        warnings=warnings,
    )


def _should_skip(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            FileNotFoundError,
            KeyError,
            FactorBatchSkip,
            FactorBacktestDataError,
            FactorBacktestEmptyResult,
            FactorBacktestParameterError,
        ),
    ):
        return True
    text = str(exc)
    return any(token in text for token in ("缺少", "没有可用", "为空", "不存在", "overlap", "missing"))


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
    transient_warnings: list[str] = []

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
            "execution_version": EXECUTION_VERSION,
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

    manager.start()
    try:
        try:
            from app.services.data.engine import DataEngine
            data_context = DataEngine.get_instance()
            data_release_id = getattr(data_context, "release_id", "unknown")
            batch_key = _stable_hash({
                "as_of_date": profile.as_of_date,
                "profile_hash": profile_hash,
                "catalog_version": catalog_version,
                "data_release_id": data_release_id,
                "execution_version": EXECUTION_VERSION,
                "metric_version": METRIC_VERSION,
            })
            existing = get_repository().get_batch_by_key(batch_key) if not dry_run else None
            # 已完成批次无需重新扫描行情；这也是任务计划重复触发时的快速路径。
            if existing and not force_retry and existing["status"] == "completed" and not dry_run:
                return existing
            preflight = _preflight(
                profile,
                len(items),
                data_context=data_context,
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
                "data_release_id": data_release_id,
                "execution_version": EXECUTION_VERSION,
                "metric_version": METRIC_VERSION,
                "preflight": preflight,
            }

        repository = get_repository()
        batch_spec_hash = _stable_hash({
            "profile": profile_payload,
            "catalog_version": catalog_version,
            "data_release_id": data_release_id,
            "execution_version": EXECUTION_VERSION,
            "metric_version": METRIC_VERSION,
        })
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
                execution_version=EXECUTION_VERSION,
                data_release_id=data_release_id,
                spec_hash=batch_spec_hash,
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
                data_release_id=data_release_id,
                spec_hash=_factor_spec(profile, item).identity(
                    data_release_id=data_release_id
                ),
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

        pending: dict[Any, tuple[FactorCatalogItem, str, FactorBacktestSpec, int]] = {}

        def submit_spec(
            item: FactorCatalogItem,
            factor_run_id: str,
            spec: FactorBacktestSpec,
            attempt: int,
        ) -> None:
            """向唯一 Manager 提交统一任务；等待只发生在协调器线程。"""

            while True:
                try:
                    def run_policy(execute):
                        return _run_cached_standard_factor_backtest(
                            spec,
                            execute,
                            data_context=DataEngine.get_instance(),
                        )

                    experiment = FactorBacktestExperiment(
                        spec,
                        run_policy=run_policy,
                    )
                    spec_hash = spec.identity(data_release_id=data_release_id)
                    handle = manager.submit(
                        experiment,
                        key=f"factor-spec:{spec_hash}",
                        lane="batch",
                        metadata={
                            "type": "factor_backtest",
                            "factor": item.factor_name,
                            "spec_hash": spec_hash,
                            "attempt": attempt,
                        },
                    )
                    break
                except ExperimentQueueFullError:
                    time.sleep(0.05)
            pending[handle.future] = (item, factor_run_id, spec, attempt)

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
                spec = _factor_spec(profile, item)
                repository.mark_factor_running(factor_run_id)
                submit_spec(item, factor_run_id, spec, 0)
            if not pending:
                break
            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            # 即使两个 future 同时完成，也一次只消费一个结果并补一个任务。
            # 这样“一个批量因子进入终态，才提交下一个”在业务代码层面是
            # 明确且可测试的，而不是依赖 wait 返回集合的偶然顺序。
            future = next(iter(done))
            item, factor_run_id, spec, attempt = pending.pop(future)
            try:
                execution: FactorBacktestResult = future.result()
                outcome = _outcome_from_result(
                    profile,
                    execution,
                    started=time.perf_counter(),
                    retry_count=attempt,
                )
            except Exception as exc:  # pragma: no cover - defensive manager guard
                if not _should_skip(exc) and attempt == 0:
                    # 仅对运行时错误重试一次；重试提交的仍是同一规格和同一任务类。
                    submit_spec(item, factor_run_id, spec, 1)
                    continue
                outcome = FactorOutcome(
                    status="skipped" if _should_skip(exc) else "failed",
                    retry_count=attempt,
                    error_code=("data_unavailable" if _should_skip(exc) else "runtime_error"),
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
            for warning in outcome.warnings:
                if warning not in transient_warnings:
                    transient_warnings.append(warning)
            completed_count += 1
            emit_progress()
            repository.refresh_batch_counts(batch_id)
    finally:
        # Manager 属于 FastAPI lifespan；批量业务不得关闭全局行情运行时或 worker。
        pass

    summary = repository.refresh_batch_counts(batch_id, final=True)
    if transient_warnings:
        # 告警只属于本次批量运行摘要，不写入历史表结构。
        summary["warnings"] = transient_warnings
    return summary


class FactorBacktestBatchCoordinator:
    """因子批量回测业务用例的异步协调器。

    ``batch_window`` 固定为 2：协调器只向 Manager 提交两个尚未完成的
    ``FactorBacktestExperiment``，任意一个进入终态后才补充一个新的因子。
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
    "FactorBacktestBatchCoordinator",
    "FactorBatchSkip",
    "FactorCatalogItem",
    "FactorOutcome",
    "METRIC_VERSION",
    "EXECUTION_VERSION",
    "run_factor_backtest_batch",
]
