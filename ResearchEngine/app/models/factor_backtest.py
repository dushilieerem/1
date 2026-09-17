"""因子回测的不可变规格与标准结果契约。

入口层只负责把自己的 DTO 转换成 :class:`FactorBacktestSpec`。规格之后的
所有计算都由 BacktestEngine 统一组织；任务来源、缓存、重试和保存位置不会进入
计算身份。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

def _dump_asset(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _dump_asset(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump_asset(item) for item in value]
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class FactorBacktestSpec:
    """一次因子回测的完整计算输入。

    规格只表达调用方提交的回测参数，不携带 ``BaseFactor`` 等运行期对象。
    因子由 ``FactorEngine`` 根据名称、因子库和源码在任务执行时私有加载。
    """

    factor_name: str
    factor_source_hash: str = ""
    factor_code: str | None = field(default=None, compare=False, repr=False)
    library_names: tuple[str, ...] = ()
    factor_params: tuple[tuple[str, Any], ...] = ()
    universe: str | tuple[str, ...] = "CSI500"
    universe_snapshot: Any = field(default=None, compare=False, repr=False)
    start: str | None = None
    end: str | None = None
    benchmark: str = "CSI300"
    benchmark_snapshot: Any = field(default=None, compare=False, repr=False)
    portfolio_type: str = "long_only"
    rebalance_days: int = 1
    groups: int | None = 5
    stock_num: int = 100
    forward_return_days: int = 1
    commission_rate: float = 0.0
    stamp_tax: float = 0.0
    slippage_rate: float = 0.0
    filter_limit_up: bool = False
    filter_suspended: bool = False
    filters_enabled: bool = False
    winsorize: int = 0
    standardize: int = 0
    analysis_level: str = "core"
    engine: str = "native"
    initial_capital: float = 1_000_000.0
    strict_as_of: bool = True
    periods_per_year: int = 252
    data_dir: str | None = field(default=None, compare=False, repr=False)
    output_path: str | None = field(default=None, compare=False, repr=False)
    storage: str = field(default="csv", compare=False, repr=False)
    execution_version: str = "factor-execution-v5"
    metric_version: str = "factor-scorecard-v3"

    def computation_payload(self) -> dict[str, Any]:
        """返回不含入口/持久化策略的规范化计算身份。"""

        return _jsonable({
            "factor_name": self.factor_name,
            "factor_source_hash": self.factor_source_hash,
            "library_names": self.library_names,
            "factor_params": self.factor_params,
            "universe": self.universe,
            "universe_snapshot": _dump_asset(self.universe_snapshot),
            "start": self.start,
            "end": self.end,
            "benchmark": self.benchmark,
            "benchmark_snapshot": _dump_asset(self.benchmark_snapshot),
            "portfolio_type": self.portfolio_type,
            "rebalance_days": self.rebalance_days,
            "groups": self.groups,
            "stock_num": self.stock_num,
            "forward_return_days": self.forward_return_days,
            # 因子回测固定为毛收益；保留 Spec 字段接收旧请求，但费用
            # 参数不再是实际计算身份，避免同一结果因无效成本参数重复缓存。
            "commission_rate": 0.0,
            "stamp_tax": 0.0,
            "slippage_rate": 0.0,
            "filter_limit_up": self.filter_limit_up,
            "filter_suspended": self.filter_suspended,
            "filters_enabled": self.filters_enabled,
            "winsorize": self.winsorize,
            "standardize": self.standardize,
            "analysis_level": self.analysis_level,
            "engine": self.engine,
            "initial_capital": self.initial_capital,
            "strict_as_of": self.strict_as_of,
            "periods_per_year": self.periods_per_year,
            "execution_version": self.execution_version,
            "metric_version": self.metric_version,
        })

    def identity(self, *, data_release_id: str | None = None) -> str:
        payload = {
            "spec": self.computation_payload(),
            "data_release_id": data_release_id,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.computation_payload(),
            "spec_hash": self.identity(),
        }


@dataclass
class FactorBacktestResult:
    """统一执行结果；API 和批量仓库只做各自的投影。"""

    spec: FactorBacktestSpec
    result_manager: Any
    benchmark_equity: Any
    quantile_metrics: tuple[Any, ...] = ()
    predictive_metrics: dict[str, Any] = field(default_factory=dict)
    data_release_id: str | None = None
    actual_end: str | None = None

    @property
    def equity_curve(self):
        return self.result_manager.equity_curve

    @property
    def returns(self):
        return self.result_manager.returns

    @property
    def positions(self):
        return self.result_manager.positions

    @property
    def rebalance_logs(self):
        return getattr(self.result_manager, "rebalance_logs", None)

    @property
    def metrics(self):
        return self.result_manager.metrics

    @property
    def factor_analysis(self):
        return getattr(self.result_manager, "factor_analysis", {}) or {}

    @property
    def spec_hash(self) -> str:
        return self.spec.identity(
            data_release_id=self.data_release_id,
        )

    def provenance(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "spec_hash": self.spec_hash,
            "factor_source_hash": self.spec.factor_source_hash,
            "data_release_id": self.data_release_id,
            "execution_version": self.spec.execution_version,
            "metric_version": self.spec.metric_version,
            "actual_end": self.actual_end,
        }


__all__ = ["FactorBacktestSpec", "FactorBacktestResult"]
