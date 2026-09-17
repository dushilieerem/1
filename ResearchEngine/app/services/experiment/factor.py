"""历史因子分析的纯辅助函数。

因子回测的计算流程已经迁移到 :class:`app.services.backtest.BacktestEngine`。
本模块只保留仍被旧分析引用的纯辅助函数，不承载 Experiment、因子组合、
收益或指标计算流程。
"""

from __future__ import annotations

import math

import pandas as pd

from app.services.data.engine import DataEngine
from app.services.metric.engine import MetricEngine
from app.models.data import Panel
from app.models.metric import MetricContext
from app.services.results.manager import ResultManager


def _daily_ic_series(
    factor_values: pd.DataFrame,
    forward_returns: pd.DataFrame,
) -> pd.DataFrame:
    """计算日频 Pearson IC 与每个截面的有效样本数。"""

    dates = factor_values.index.intersection(forward_returns.index)
    symbols = factor_values.columns.intersection(forward_returns.columns)
    if dates.empty or symbols.empty:
        return pd.DataFrame(columns=["value", "sample_size"])
    factor = factor_values.loc[dates, symbols]
    returns = forward_returns.loc[dates, symbols]
    valid = factor.notna() & returns.notna()
    result = pd.DataFrame({
        "value": factor.corrwith(returns, axis=1),
        "sample_size": valid.sum(axis=1),
    }).dropna(subset=["value"])
    return result[result["sample_size"] >= 2]


def _predictive_summary(
    factor_values: pd.DataFrame,
    forward_returns: pd.DataFrame,
    periods_per_year: int = 252,
) -> dict[str, float | int | str | None]:
    """计算兼容批量仓库的 IC/RankIC 汇总。"""

    empty = {
        "ic_mean": None,
        "rank_ic_mean": None,
        "ic_std": None,
        "ic_ir": None,
        "valid_days": 0,
        "actual_start": None,
        "actual_end": None,
    }
    daily = _daily_ic_series(factor_values, forward_returns)
    if daily.empty:
        return empty
    dates = factor_values.index.intersection(forward_returns.index)
    symbols = factor_values.columns.intersection(forward_returns.columns)
    factor = factor_values.loc[dates, symbols]
    returns = forward_returns.loc[dates, symbols]
    valid = factor.notna() & returns.notna()
    enough = valid.sum(axis=1) >= 2
    factor, returns = factor.loc[enough], returns.loc[enough]
    rank_ic = factor.rank(axis=1).corrwith(returns.rank(axis=1), axis=1).dropna()
    ic = daily["value"]
    mean = float(ic.mean())
    std = float(ic.std(ddof=1)) if len(ic) > 1 else None
    return {
        "ic_mean": mean,
        "rank_ic_mean": float(rank_ic.mean()) if not rank_ic.empty else None,
        "ic_std": std,
        "ic_ir": None if std is None else (
            0.0 if std == 0 else float(mean / std * math.sqrt(periods_per_year))
        ),
        "valid_days": int(len(ic)),
        "actual_start": pd.Timestamp(ic.index.min()).date().isoformat(),
        "actual_end": pd.Timestamp(ic.index.max()).date().isoformat(),
    }


def _apply_factor_batch_filters(
    factor_values: pd.DataFrame,
    panel: Panel,
    config: ConfigManager,
) -> pd.DataFrame:
    """旧内部调用兼容；有效池构造统一交给 QuantCore DataEngine。"""

    if not config.get("factor_batch.filters_enabled", False):
        return factor_values.copy()
    info = DataEngine().build_filter_mask(
        panel,
        filter_suspended=bool(config.get("filter_suspended", False)),
        filter_limit_up=bool(config.get("filter_limit_up", False)),
    )
    eligible = info["mask"].reindex(
        index=factor_values.index, columns=factor_values.columns
    ).fillna(False).astype(bool)
    return factor_values.mask(~eligible)


def _industry_equity_analysis(
    factor_values: pd.DataFrame,
    forward_returns: pd.DataFrame,
    industry_map: pd.Series,
    groups: int,
) -> tuple[dict[str, pd.Series], dict[str, pd.DataFrame]]:
    """保留旧报告需要的行业净值纯函数。"""

    dates = factor_values.index.intersection(forward_returns.index)
    symbols = factor_values.columns.intersection(forward_returns.columns)
    industries = industry_map.reindex(symbols).dropna()
    symbols = symbols.intersection(industries.index)
    if dates.empty or symbols.empty:
        return {}, {}
    industry_returns: dict[str, list[tuple[object, float]]] = {}
    group_returns: dict[str, list[tuple[object, dict[str, float]]]] = {}
    for date in dates:
        frame = pd.DataFrame({
            "factor": factor_values.loc[date, symbols],
            "return": forward_returns.loc[date, symbols],
            "industry": industries.reindex(symbols),
        }).dropna()
        for industry, values in frame.groupby("industry", sort=True):
            name = str(industry)
            industry_returns.setdefault(name, []).append(
                (date, float(values["return"].mean()))
            )
            if len(values) < groups:
                continue
            ranks = values["factor"].rank(
                pct=True, method="average", ascending=False
            )
            labels = ranks.mul(groups).apply(math.ceil).clip(upper=groups).astype(int)
            rows = {
                f"G{number}": float(values.loc[labels == number, "return"].mean())
                for number in range(1, groups + 1)
            }
            if all(pd.notna(value) for value in rows.values()):
                group_returns.setdefault(name, []).append((date, rows))
    return (
        {
            name: 1.0 + pd.Series(dict(rows)).sort_index().cumsum()
            for name, rows in industry_returns.items()
        },
        {
            name: 1.0 + pd.DataFrame(dict(rows)).T.sort_index().cumsum()
            for name, rows in group_returns.items()
        },
    )


__all__ = [
    "_apply_factor_batch_filters",
    "_daily_ic_series",
    "_industry_equity_analysis",
    "_predictive_summary",
]
