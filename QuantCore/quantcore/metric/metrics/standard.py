"""标准指标实现（各自实现 ``BaseMetric``）。

依据 ``docs/04-类设计.md`` MetricEngine 节，共 10 个指标，分四类：

- 收益类：``AnnualReturn``
- 风险类：``SharpeRatio`` / ``SortinoRatio`` / ``CalmarRatio`` / ``MaxDrawdown`` / ``Volatility``
- 因子类：``InformationCoefficient`` (IC) / ``RankIC``
- 交易类：``WinRate`` / ``Turnover``
"""

from __future__ import annotations

import math
from typing import Dict

import numpy as np
import pandas as pd

from quantcore.backtest.result import returns_from_equity
from quantcore.metric.base import BaseMetric
from quantcore.metric.context import MetricContext

_NAN = float("nan")


def _returns(ctx: MetricContext) -> pd.Series:
    """从 ctx 取收益率；缺则由 equity_curve 推导。"""
    if ctx.returns is not None and not ctx.returns.empty:
        return ctx.returns
    return returns_from_equity(ctx.equity_curve)


# ---------------- 收益类 ----------------


class AnnualReturn(BaseMetric):
    """年化收益率。``calculate(equity_curve)``"""

    name = "annual_return"

    def calculate(self, ctx: MetricContext) -> float:
        eq = ctx.equity_curve
        if eq is None or eq.empty or len(eq) < 2:
            return _NAN
        total = eq.iloc[-1] / eq.iloc[0] - 1.0
        n = len(eq) - 1
        if n <= 0:
            return _NAN
        return float((1.0 + total) ** (ctx.periods_per_year / n) - 1.0)


# ---------------- 风险类 ----------------


class SharpeRatio(BaseMetric):
    """夏普比率（无风险利率取 0）。``calculate(returns)``"""

    name = "sharpe"

    def calculate(self, ctx: MetricContext) -> float:
        r = _returns(ctx)
        if r.empty:
            return _NAN
        std = r.std()
        if std == 0 or math.isnan(std):
            return 0.0
        return float(r.mean() / std * math.sqrt(ctx.periods_per_year))


class SortinoRatio(BaseMetric):
    """索提诺比率。``calculate(returns)``"""

    name = "sortino"

    def calculate(self, ctx: MetricContext) -> float:
        r = _returns(ctx)
        if r.empty:
            return _NAN
        # 下行偏差：min(r, 0) 的均方根（对全部 N 期求均值）
        downside = np.minimum(r, 0.0)
        dd_std = math.sqrt((downside ** 2).mean())
        if dd_std == 0:
            return 0.0 if r.mean() == 0 else float("inf")
        return float(r.mean() / dd_std * math.sqrt(ctx.periods_per_year))


class MaxDrawdown(BaseMetric):
    """最大回撤（返回负值，如 -0.082）。``calculate(equity_curve)``"""

    name = "max_drawdown"

    def calculate(self, ctx: MetricContext) -> float:
        eq = ctx.equity_curve
        if eq is None or eq.empty:
            return _NAN
        running_max = eq.cummax()
        drawdown = (eq - running_max) / running_max
        return float(drawdown.min())


class Volatility(BaseMetric):
    """年化波动率。``calculate(returns)``"""

    name = "volatility"

    def calculate(self, ctx: MetricContext) -> float:
        r = _returns(ctx)
        if r.empty:
            return _NAN
        return float(r.std() * math.sqrt(ctx.periods_per_year))


class CalmarRatio(BaseMetric):
    """卡玛比率 = 年化收益 / |最大回撤|。``calculate(equity_curve)``"""

    name = "calmar"

    def calculate(self, ctx: MetricContext) -> float:
        annual = AnnualReturn().calculate(ctx)
        mdd = MaxDrawdown().calculate(ctx)
        if math.isnan(annual) or math.isnan(mdd) or mdd == 0:
            return _NAN
        return float(annual / abs(mdd))


# ---------------- 因子类 ----------------


def _aligned_factor_returns(ctx: MetricContext):
    """对齐因子值与远期收益，返回 (factor, fwd) 同形状 DataFrame。"""
    fv, fr = ctx.factor_values, ctx.forward_returns
    if fv is None or fr is None or fv.empty or fr.empty:
        return None, None
    common_dates = fv.index.intersection(fr.index)
    common_symbols = fv.columns.intersection(fr.columns)
    fv = fv.loc[common_dates, common_symbols]
    fr = fr.loc[common_dates, common_symbols]
    return fv, fr


class InformationCoefficient(BaseMetric):
    """IC：因子值与远期收益的截面 Pearson 相关均值。"""

    name = "ic"

    def calculate(self, ctx: MetricContext) -> float:
        fv, fr = _aligned_factor_returns(ctx)
        if fv is None:
            return _NAN
        # 逐行（按日期）截面相关，一次向量化完成；NaN 行自动丢弃
        corrs = fv.corrwith(fr, axis=1).dropna()
        if corrs.empty:
            return _NAN
        return float(corrs.mean())


class RankIC(BaseMetric):
    """RankIC：因子值与远期收益的截面 Spearman 相关均值。"""

    name = "rank_ic"

    def calculate(self, ctx: MetricContext) -> float:
        fv, fr = _aligned_factor_returns(ctx)
        if fv is None:
            return _NAN
        # 截面排名后求 Pearson 相关（等价于 Spearman），逐行向量化
        corrs = fv.rank(axis=1).corrwith(fr.rank(axis=1), axis=1).dropna()
        if corrs.empty:
            return _NAN
        return float(corrs.mean())


# ---------------- 交易类 ----------------


class WinRate(BaseMetric):
    """胜率：正收益占比。``calculate(returns)``"""

    name = "win_rate"

    def calculate(self, ctx: MetricContext) -> float:
        r = _returns(ctx)
        if r.empty:
            return _NAN
        return float((r > 0).mean())


class Turnover(BaseMetric):
    """换手率：持仓权重前后期变化幅度均值。``calculate(positions)``"""

    name = "turnover"

    def calculate(self, ctx: MetricContext) -> float:
        pos = ctx.positions
        if pos is None or pos.empty or len(pos) < 2:
            return _NAN
        diff = pos.diff().abs().iloc[1:]
        # 单边换手 = sum(|Δw|) / 2
        turnover = diff.sum(axis=1) / 2.0
        return float(turnover.mean())


#: 默认指标名称集合（对应 PRD：年化收益/最大回撤/calmar/胜率/IC 等）
DEFAULT_METRIC_NAMES = [
    "annual_return",
    "sharpe",
    "sortino",
    "calmar",
    "max_drawdown",
    "volatility",
    "ic",
    "rank_ic",
    "win_rate",
    "turnover",
]


def default_metrics() -> Dict[str, BaseMetric]:
    """返回全部标准指标的 ``{name: instance}`` 字典。"""
    instances = [
        AnnualReturn(), SharpeRatio(), SortinoRatio(), CalmarRatio(),
        MaxDrawdown(), Volatility(), InformationCoefficient(), RankIC(),
        WinRate(), Turnover(),
    ]
    return {m.name: m for m in instances}
