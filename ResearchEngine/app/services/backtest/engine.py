"""因子回测的完整流程编排器。

``BacktestEngine`` 是应用层唯一的因子回测入口：它把共享的行情上下文
依次交给 DataEngine、FactorEngine、PortfolioEngine 和 MetricEngine，
再组装现有的高层 ``FactorBacktestResult``。策略回测仍保留自己的旧
Native/Event 路径；本文件不调用策略信号或旧因子执行算法。
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

from app.services.data.engine import DataEngine
from app.services.factor.engine import FactorEngine
from app.services.metric.engine import MetricEngine
from app.services.portfolio.engine import PortfolioEngine
from app.services.results.manager import ResultManager
from app.database.results.storage.csv_storage import CSVStorage
from app.database.results.storage.parquet_storage import ParquetStorage
from app.database.results.storage.sqlite_storage import SQLiteStorage
from app.services.factor.backtest_support import _benchmark_equity
from app.services.factor.errors import (
    FactorBacktestDataError,
    FactorBacktestEmptyResult,
    FactorBacktestParameterError,
    FactorBacktestRuntimeError,
)
from app.models.factor_backtest import FactorBacktestResult, FactorBacktestSpec


_STORAGE_MAP = {
    "csv": CSVStorage,
    "parquet": ParquetStorage,
    "sqlite": SQLiteStorage,
}
_PRICE_FIELDS = ("open", "high", "low", "close")
def _date(value: Any) -> str:
    try:
        return pd.Timestamp(value).date().isoformat()
    except (TypeError, ValueError) as exc:
        raise FactorBacktestParameterError(f"无效的回测截止日期: {value!r}") from exc


def _empty_predictive() -> dict[str, Any]:
    return {
        "ic_mean": None,
        "rank_ic_mean": None,
        "ic_std": None,
        "ic_ir": None,
        "valid_days": 0,
        "actual_start": None,
        "actual_end": None,
    }


class BacktestEngine:
    """组织一次完整因子回测。"""

    def __init__(
        self,
        *,
        portfolio_engine: PortfolioEngine | None = None,
        metric_engine: MetricEngine | None = None,
    ) -> None:
        self.portfolio_engine = portfolio_engine or PortfolioEngine()
        self.metric_engine = metric_engine or MetricEngine()

    @staticmethod
    def _storage(kind: str):
        if kind not in _STORAGE_MAP:
            raise ValueError(f"未知 storage {kind!r}，可选: {list(_STORAGE_MAP)}")
        return _STORAGE_MAP[kind]()

    def run(
        self,
        spec: FactorBacktestSpec,
    ) -> FactorBacktestResult:
        """执行 Data → Factor → Portfolio → Metric 的完整因子回测。"""

        started = time.perf_counter()
        timings: dict[str, float] = {}
        stage_started = started
        data_engine = DataEngine.get_instance()
        factor_engine = FactorEngine(spec)
        timings["data_prepare"] = round(time.perf_counter() - stage_started, 6)
        actual_end = factor_engine.actual_end
        if actual_end is None:  # pragma: no cover - constructor contract
            raise FactorBacktestRuntimeError("FactorEngine 未确定实际数据截止日")
        data_release_id = getattr(data_engine, "release_id", "unknown")

        stage_started = time.perf_counter()
        factor_values = factor_engine.compute()
        timings["factor_compute"] = round(time.perf_counter() - stage_started, 6)

        # FactorEngine 已按本次 spec 的日期范围准备数据。PortfolioEngine 在该范围内
        # 先 shift(-horizon)，再按因子日期对齐；范围末端没有足够未来价格时，评价
        # 标签自然为空，不能影响当期组合构建。
        close = factor_engine.market_field("close")
        common = factor_values.columns.intersection(close.columns)
        if common.empty:
            raise FactorBacktestParameterError(
                "因子返回值未包含股票池中的标的。指数序列（如 self.csi300.close）"
                "不能直接作为股票因子返回；请与 self.close 按日期对齐后构造股票宽表。"
            )
        factor_values = factor_values.loc[:, common]
        close = close.loc[:, common]
        if factor_values.empty or close.empty:
            raise FactorBacktestEmptyResult("收益确认区间内因子计算结果为空")

        stage_started = time.perf_counter()
        try:
            portfolio = self.portfolio_engine.build(
                factor_values,
                close,
                groups=spec.groups,
                portfolio_type=spec.portfolio_type,
                rebalance=spec.rebalance_days,
                stock_num=spec.stock_num,
                horizon=spec.forward_return_days,
                # 完整调仓明细会逐日逐标的展开，核心回测不需要它；只有
                # 显式请求 full 分析时保留旧行为。
                include_rebalance_logs=spec.analysis_level == "full",
            )
        except (FactorBacktestDataError, FactorBacktestEmptyResult, FactorBacktestParameterError):
            raise
        except (TypeError, ValueError) as exc:
            raise FactorBacktestParameterError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise FactorBacktestRuntimeError(f"组合构建失败: {type(exc).__name__}: {exc}") from exc
        timings["portfolio_build"] = round(time.perf_counter() - stage_started, 6)

        industry_map = None
        market_fields: dict[str, pd.DataFrame] = {}
        if spec.analysis_level == "full":
            industry_map = data_engine.get_industry_map(
                spec.data_dir or str(data_engine.data_dir)
            )
            for field in ("current_mv", "pb_mrq"):
                try:
                    if factor_engine.has_market_field(field):
                        market_fields[field] = factor_engine.market_field(field)
                except Exception:  # noqa: BLE001 - 可选增强字段失败时降级
                    pass

        def load_benchmark(dates: pd.DatetimeIndex) -> pd.Series:
            try:
                return _benchmark_equity(
                    spec.benchmark,
                    spec.benchmark_snapshot,
                    dates,
                    data_engine=data_engine,
                )
            except NotImplementedError as exc:
                raise FactorBacktestDataError(str(exc)) from exc
            except (FileNotFoundError, KeyError, ValueError) as exc:
                raise FactorBacktestDataError(str(exc)) from exc

        stage_started = time.perf_counter()
        try:
            evaluation = self.metric_engine.evaluate_factor_portfolio(
                portfolio,
                commission_rate=spec.commission_rate,
                stamp_tax=spec.stamp_tax,
                slippage_rate=spec.slippage_rate,
                periods_per_year=spec.periods_per_year,
                analysis_level=spec.analysis_level,
                benchmark_loader=load_benchmark,
                industry_map=industry_map,
                market_fields=market_fields,
                rebalance=spec.rebalance_days,
                groups=spec.groups,
            )
        except (FactorBacktestDataError, FactorBacktestEmptyResult, FactorBacktestParameterError):
            raise
        except (TypeError, ValueError) as exc:
            raise FactorBacktestParameterError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise FactorBacktestRuntimeError(f"指标评价失败: {type(exc).__name__}: {exc}") from exc
        timings["metric_evaluate"] = round(time.perf_counter() - stage_started, 6)

        preprocess = {
            "winsorize": spec.winsorize,
            "standardize": spec.standardize,
            "order": ["eligibility_mask", "winsorize", "standardize"],
            "axis": "cross_sectional",
        }
        result = ResultManager(
            metrics=evaluation["metrics"],
            factor_values=factor_values,
            equity_curve=evaluation["equity_curve"],
            returns=evaluation["returns"],
            positions=evaluation["positions"],
            rebalance_logs=portfolio["rebalance_logs"],
            target_weights=portfolio["target_weights"],
            forward_returns=portfolio["forward_returns"],
            storage=self._storage(spec.storage),
            meta={
                "factor": factor_engine.factor_metadata()["name"],
                "author": factor_engine.factor_metadata()["author"],
                "universe": spec.universe,
                "start_date": spec.start,
                "end_date": actual_end,
                "factor_price_adjustment": "hfq",
                "factor_price_source": "data_engine.open_high_low_close",
                "factor_price_fields": list(_PRICE_FIELDS),
                "factor_price_precision": "source_precision_no_rounding",
                "return_price_adjustment": "hfq",
                "return_price_source": "data_engine.close",
                "return_price_precision": "source_precision_no_rounding",
                "factor_preprocess": {
                    **preprocess,
                },
                **factor_engine.result_diagnostics(),
                "transaction_summary": evaluation["transaction_summary"],
                "execution_version": spec.execution_version,
                "metric_version": spec.metric_version,
                "data_release_id": data_release_id,
                "actual_end": actual_end,
                "engine": "BacktestEngine",
                "timings_seconds": {
                    **timings,
                    "total": round(time.perf_counter() - started, 6),
                },
            },
        )
        result.factor_analysis = evaluation.get("factor_analysis", {})
        result.meta["spec_hash"] = spec.identity(data_release_id=data_release_id)
        if spec.output_path:
            result.save(spec.output_path)
        return FactorBacktestResult(
            spec=spec,
            result_manager=result,
            benchmark_equity=evaluation["benchmark_equity"],
            quantile_metrics=tuple(evaluation.get("quantile_metrics", ())),
            predictive_metrics={
                key: evaluation.get("factor_analysis", {}).get(
                    "predictive_summary", _empty_predictive()
                ).get(key)
                for key in ("ic_mean", "rank_ic_mean", "ic_ir")
            },
            data_release_id=data_release_id,
            actual_end=actual_end,
        )


__all__ = ["BacktestEngine"]
