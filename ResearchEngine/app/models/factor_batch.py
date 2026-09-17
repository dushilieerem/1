"""因子批量回测配置与结果数据。"""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class FactorCatalogItem:
    library_name: str
    factor_name: str
    source_hash: str
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
    filter_limit_up: bool = False
    filter_suspended: bool = False
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
    warnings: tuple[str, ...] = ()
