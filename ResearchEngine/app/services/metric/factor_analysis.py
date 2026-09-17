"""因子组合的高级评价辅助函数。

这些函数只接收已经准备好的因子、收益和市场数据，不负责读取行情或
组装回测流程。对外结果类型暂时保留 ``QuantileMetric``，由上层序列化
代码继续复用现有 API 契约；计算入口统一由 ``MetricEngine`` 调用。
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.schemas.backtest import QuantileMetric


def _finite_series(series: pd.Series) -> pd.Series:
    """将序列转成可参与指标计算的有限数值。"""

    values = pd.to_numeric(series, errors="coerce")
    return values.replace([float("inf"), float("-inf")], pd.NA).dropna()


def _safe_metric(value) -> float | None:
    """将指标值转换成 JSON 安全的浮点数。"""

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _geometric_annual_return(
    returns: pd.Series,
    periods_per_year: int,
    observations: int | None = None,
) -> float | None:
    """按累计收益计算 CAGR；``observations`` 控制年化指数。"""

    clean_returns = _finite_series(returns)
    if clean_returns.empty:
        return None
    count = int(observations if observations is not None else len(clean_returns))
    if count <= 0:
        return None
    cumulative_factor = float((1.0 + clean_returns).prod())
    if cumulative_factor < 0:
        return None
    return _safe_metric(cumulative_factor ** (periods_per_year / count) - 1.0)


def _daily_ic(factor: pd.DataFrame, future: pd.DataFrame) -> pd.DataFrame:
    """计算逐日截面 IC 及有效样本数。"""

    dates = factor.index.intersection(future.index)
    symbols = factor.columns.intersection(future.columns)
    if dates.empty or symbols.empty:
        return pd.DataFrame(columns=["value", "sample_size"])
    left, right = factor.loc[dates, symbols], future.loc[dates, symbols]
    valid = left.notna() & right.notna()
    result = pd.DataFrame({
        "value": left.corrwith(right, axis=1),
        "sample_size": valid.sum(axis=1),
    }).dropna(subset=["value"])
    return result[result["sample_size"] >= 2]


def _industry_equity(
    factor_values: pd.DataFrame,
    future: pd.DataFrame,
    industry_map: pd.Series,
    groups: int,
) -> tuple[dict[str, pd.Series], dict[str, pd.DataFrame]]:
    """计算行业等权及行业内分组净值。"""

    dates = factor_values.index.intersection(future.index)
    symbols = factor_values.columns.intersection(future.columns)
    industries = industry_map.reindex(symbols).dropna()
    symbols = symbols.intersection(industries.index)
    if dates.empty or symbols.empty:
        return {}, {}
    # 只按行业循环；行业内日期×标的运算全部保持宽表向量化。旧实现是
    # ``for date -> for industry -> for group``，在 full 分析中会重复创建
    # 数千个小 DataFrame，成为另一处隐蔽的双层循环。
    industry_returns: dict[str, pd.Series] = {}
    industry_group_equity: dict[str, pd.DataFrame] = {}
    for industry in pd.unique(industries):
        industry_symbols = symbols[industries.reindex(symbols).eq(industry)]
        if len(industry_symbols) == 0:
            continue
        factor_slice = factor_values.loc[dates, industry_symbols]
        return_slice = future.loc[dates, industry_symbols]
        valid = factor_slice.notna() & return_slice.notna()
        industry_return = return_slice.where(valid).mean(axis=1)
        name = str(industry)
        industry_returns[name] = industry_return.dropna()

        valid_count = valid.sum(axis=1)
        if not (valid_count >= groups).any():
            continue
        ranks = factor_slice.where(valid).rank(
            axis=1,
            pct=True,
            method="average",
            ascending=False,
        )
        labels = np.ceil(
            ranks.to_numpy(dtype=float, na_value=np.nan) * groups
        )
        labels = np.clip(labels, 1, groups)
        group_returns = {
            f"G{number}": return_slice.where(labels == number).mean(axis=1)
            for number in range(1, groups + 1)
        }
        group_frame = pd.DataFrame(group_returns)
        eligible_dates = (valid_count >= groups) & group_frame.notna().all(axis=1)
        if eligible_dates.any():
            industry_group_equity[name] = 1.0 + group_frame.loc[eligible_dates].cumsum()

    industry_equity = {
        name: 1.0 + returns.sort_index().cumsum()
        for name, returns in industry_returns.items()
    }
    return industry_equity, industry_group_equity


def _compute_quantile_metrics(
    layered_equity: pd.DataFrame,
    benchmark_equity: pd.Series,
    periods_per_year: int = 252,
    *,
    layered_returns: pd.DataFrame | None = None,
    relative_benchmark_returns: pd.Series | None = None,
) -> list[QuantileMetric]:
    """按当前对齐口径计算分组及基准指标。"""

    if layered_equity is None or layered_equity.empty:
        return []
    if benchmark_equity is None or benchmark_equity.empty:
        return []

    annualization = math.sqrt(periods_per_year)
    layered_returns = layered_returns if layered_returns is not None else pd.DataFrame()

    def absolute_metrics(
        equity: pd.Series,
        returns: pd.Series,
        *,
        ddof: int,
        annualization_observations: int | None = None,
        include_initial_return_in_drawdown: bool = False,
    ) -> tuple[dict[str, float | None], pd.Series]:
        clean_equity = _finite_series(equity)
        returns = _finite_series(returns)
        return_std = returns.std(ddof=ddof)
        metrics = {
            "annual_return": _geometric_annual_return(
                returns,
                periods_per_year,
                observations=annualization_observations,
            ),
            "volatility": (
                _safe_metric(return_std * annualization)
                if not pd.isna(return_std) else None
            ),
            "sharpe": None,
            "max_drawdown": None,
        }
        if not returns.empty and not pd.isna(return_std):
            metrics["sharpe"] = _safe_metric(
                0.0 if return_std == 0
                else returns.mean() / return_std * annualization
            )

        drawdown_equity = clean_equity
        if include_initial_return_in_drawdown and not returns.empty:
            drawdown_equity = pd.concat([
                pd.Series([1.0]),
                (1.0 + returns).cumprod(),
            ])
        if not drawdown_equity.empty:
            running_max = drawdown_equity.cummax()
            drawdown = (drawdown_equity - running_max).div(
                running_max.where(running_max != 0)
            )
            if not drawdown.dropna().empty:
                metrics["max_drawdown"] = _safe_metric(drawdown.min())
        return metrics, returns

    benchmark_price_returns = benchmark_equity.pct_change(fill_method=None)
    first_benchmark_date = benchmark_equity.first_valid_index()
    if first_benchmark_date is not None:
        benchmark_price_returns.loc[first_benchmark_date] = 0.0
    benchmark_price_returns = _finite_series(benchmark_price_returns)
    benchmark_cumulative_returns = pd.Series(
        dtype=float, name="benchmark_cumulative"
    )
    if first_benchmark_date is not None:
        benchmark_cumulative_returns = _finite_series(
            benchmark_equity.div(
                float(benchmark_equity.loc[first_benchmark_date])
            ) - 1.0
        ).rename("benchmark_cumulative")
    benchmark_observations = (
        len(layered_returns)
        if not layered_returns.empty
        else len(benchmark_price_returns)
    )
    benchmark_metrics, benchmark_price_returns = absolute_metrics(
        benchmark_equity,
        benchmark_price_returns,
        ddof=1,
        annualization_observations=benchmark_observations,
    )
    relative_benchmark_returns = (
        benchmark_price_returns
        if relative_benchmark_returns is None
        else _finite_series(relative_benchmark_returns)
    ).rename("benchmark")
    result = []

    for number, column in enumerate(layered_equity.columns, start=1):
        returns = (
            layered_returns[column]
            if column in layered_returns.columns
            else layered_equity[column].pct_change(fill_method=None)
        )
        absolute, returns = absolute_metrics(
            layered_equity[column],
            returns,
            ddof=1,
            annualization_observations=len(_finite_series(returns)),
            include_initial_return_in_drawdown=True,
        )
        aligned = pd.concat(
            [returns.rename("group"), relative_benchmark_returns],
            axis=1,
            join="inner",
        ).dropna()
        excess = aligned["group"] - aligned["benchmark"]

        excess_std = excess.std(ddof=1)
        common_observations = len(aligned)
        group_cumulative_factor = float((1.0 + aligned["group"]).prod())
        benchmark_cumulative_factor = float((1.0 + aligned["benchmark"]).prod())
        cumulative_excess_factor = (
            1.0 + group_cumulative_factor - benchmark_cumulative_factor
        )
        annual_excess_return = None
        if common_observations > 0 and cumulative_excess_factor >= 0:
            annual_excess_return = _safe_metric(
                cumulative_excess_factor ** (
                    periods_per_year / common_observations
                ) - 1.0
            )
        excess_volatility = (
            _safe_metric(excess_std * annualization)
            if not pd.isna(excess_std) else None
        )
        information_ratio = None
        if annual_excess_return is not None and not pd.isna(excess_std):
            information_ratio = _safe_metric(
                0.0 if excess_std == 0
                else annual_excess_return / (excess_std * annualization)
            )
        win_aligned = pd.concat(
            [returns.rename("group"), benchmark_cumulative_returns],
            axis=1,
            join="inner",
        ).dropna()
        benchmark_win_rate = (
            _safe_metric(
                (win_aligned["group"] > win_aligned["benchmark_cumulative"]).mean()
            )
            if not win_aligned.empty else None
        )

        column_name = str(column)
        if column_name.lower().startswith("layer"):
            quantile = f"Q{column_name[5:]}"
        elif column_name.upper().startswith("Q"):
            quantile = column_name.upper()
        else:
            quantile = f"Q{number}"
        result.append(QuantileMetric(
            quantile=quantile,
            **absolute,
            annual_excess_return=annual_excess_return,
            excess_volatility=excess_volatility,
            information_ratio=information_ratio,
            benchmark_win_rate=benchmark_win_rate,
        ))

    result.append(QuantileMetric(
        quantile="benchmark",
        **benchmark_metrics,
    ))
    return result


__all__ = [
    "_compute_quantile_metrics",
    "_daily_ic",
    "_finite_series",
    "_geometric_annual_return",
    "_industry_equity",
    "_safe_metric",
]
