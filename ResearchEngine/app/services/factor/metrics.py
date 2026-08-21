"""因子回测的分组、基准及相对基准指标计算。

该模块只负责把收益序列转换成 API 使用的指标对象，不负责读取行情、
加载因子或编排回测流程。``runner.py`` 保留同名兼容导入，避免已有
调用方依赖内部函数路径时发生不必要的破坏性变更。
"""

from __future__ import annotations

import math

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


def _compute_quantile_metrics(
    layered_equity: pd.DataFrame,
    benchmark_equity: pd.Series,
    periods_per_year: int = 252,
    *,
    layered_returns: pd.DataFrame | None = None,
    relative_benchmark_returns: pd.Series | None = None,
) -> list[QuantileMetric]:
    """按当前对齐口径计算分组及基准指标。

    分组指标使用 ``layered_returns`` 的完整原始收益（含首个信号到入场
    日收益），并将初始净值 1.0 置于该收益之前计算最大回撤。展示净值
    仍然只用于前端累计曲线，首日归一化不参与分组指标。基准没有这笔
    信号收益，因此从归一化基准曲线推导，首个入场日收益保留为 0，
    并使用样本标准差。相对基准
    指标使用完整的共同日收益序列；调用方应通过
    ``relative_benchmark_returns`` 传入与分组收益同长度的入场日归一化
    基准收益，首个共同日基准收益为 0。年化超额收益为共同区间的累计
    简单收益差再进行几何年化，信息比率为年化超额收益除以超额年化
    波动，胜率比较共同日期上的分组当日收益与基准累计收益。
    """
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
    "_finite_series",
    "_safe_metric",
    "_geometric_annual_return",
]
