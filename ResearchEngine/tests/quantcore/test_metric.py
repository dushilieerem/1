"""``MetricEngine`` 与各指标数值正确性测试。"""

import math

import numpy as np
import pandas as pd

from app.models.metric import MetricContext
from app.services.metric.engine import MetricEngine
from app.services.metric.metrics.standard import (
    AnnualReturn,
    CalmarRatio,
    InformationCoefficient,
    MaxDrawdown,
    RankIC,
    SharpeRatio,
    SortinoRatio,
    Turnover,
    Volatility,
    WinRate,
)


def _ctx(**kw):
    return MetricContext(periods_per_year=252, **kw)


# ---------------- 收益/风险类 ----------------

def test_max_drawdown():
    eq = pd.Series([1.0, 1.1, 0.9, 1.2], index=pd.date_range("2022-01-03", periods=4))
    mdd = MaxDrawdown().calculate(_ctx(equity_curve=eq))
    # 回撤：(0.9-1.1)/1.1 = -0.1818...
    assert math.isclose(mdd, (0.9 - 1.1) / 1.1, abs_tol=1e-6)
    assert mdd < 0


def test_annual_return():
    # 12 个月度净值，periods_per_year=12
    eq = pd.Series([1.0, 1.1], index=pd.date_range("2022-01-03", periods=2))
    ctx = MetricContext(equity_curve=eq, periods_per_year=1)
    # 1 期涨 10%，年化 10%
    assert math.isclose(AnnualReturn().calculate(ctx), 0.10, abs_tol=1e-6)


def test_sharpe():
    # 固定 returns，手算
    r = pd.Series([0.01, -0.02, 0.03, 0.0, 0.02])
    mean = r.mean()
    std = r.std()  # ddof=1
    expected = mean / std * math.sqrt(252)
    assert math.isclose(SharpeRatio().calculate(_ctx(returns=r)), expected, abs_tol=1e-6)


def test_volatility():
    r = pd.Series([0.01, -0.02, 0.03, 0.0, 0.02])
    expected = r.std() * math.sqrt(252)
    assert math.isclose(Volatility().calculate(_ctx(returns=r)), expected, abs_tol=1e-6)


def test_sortino_geq_sharpe_when_skew_positive():
    r = pd.Series([0.01, 0.02, -0.01, 0.03, 0.02, -0.005])
    sharpe = SharpeRatio().calculate(_ctx(returns=r))
    sortino = SortinoRatio().calculate(_ctx(returns=r))
    # 均值为正时，下行偏差 <= 总标准差，故 Sortino >= Sharpe
    assert sortino >= sharpe - 1e-9


def test_calmar():
    eq = pd.Series([1.0, 1.2, 1.0, 1.5], index=pd.date_range("2022-01-03", periods=4))
    ctx = MetricContext(equity_curve=eq, periods_per_year=4)
    annual = AnnualReturn().calculate(ctx)
    mdd = MaxDrawdown().calculate(ctx)
    assert math.isclose(CalmarRatio().calculate(ctx), annual / abs(mdd), abs_tol=1e-6)


# ---------------- 因子类 ----------------

def test_ic_perfect_correlation():
    # 因子值与远期收益完全正相关 -> IC ≈ 1
    idx = pd.date_range("2022-01-03", periods=5)
    fv = pd.DataFrame({"A": [1, 2, 3, 4, 5], "B": [2, 3, 4, 5, 6]}, index=idx)
    fr = fv.copy()  # 完全相关
    ic = InformationCoefficient().calculate(_ctx(factor_values=fv, forward_returns=fr))
    assert math.isclose(ic, 1.0, abs_tol=1e-6)


def test_rank_ic_negative():
    idx = pd.date_range("2022-01-03", periods=5)
    fv = pd.DataFrame({"A": [1, 2, 3, 4, 5], "B": [2, 3, 4, 5, 6]}, index=idx)
    fr = -fv.copy()  # 完全负相关
    ic = RankIC().calculate(_ctx(factor_values=fv, forward_returns=fr))
    assert math.isclose(ic, -1.0, abs_tol=1e-6)


# ---------------- 交易类 ----------------

def test_win_rate():
    r = pd.Series([0.01, -0.02, 0.03, -0.01])
    assert math.isclose(WinRate().calculate(_ctx(returns=r)), 0.5, abs_tol=1e-6)


def test_turnover():
    # 两期持仓：从全仓 A 换到全仓 B -> 单边换手 1.0
    pos = pd.DataFrame(
        {"A": [1.0, 0.0], "B": [0.0, 1.0]},
        index=pd.date_range("2022-01-03", periods=2),
    )
    # turnover = mean(|Δw|/2) ; 第一期 diff = [1,1], sum/2 = 1.0
    assert math.isclose(Turnover().calculate(_ctx(positions=pos)), 1.0, abs_tol=1e-6)


def test_metric_engine_calculate_all():
    r = pd.Series([0.01, 0.02, -0.01, 0.03])
    eq = (1 + r).cumprod()
    ctx = _ctx(equity_curve=eq, returns=r)
    engine = MetricEngine()
    result = engine.calculate_all(ctx)
    for name in ["sharpe", "volatility", "win_rate", "max_drawdown", "annual_return"]:
        assert name in result
        assert not math.isnan(result[name])


def test_metric_engine_accepts_single_metric_name_and_exposes_registry_snapshot():
    r = pd.Series([0.01, -0.02, 0.03, 0.0, 0.02])
    engine = MetricEngine()

    result = engine.calculate("sharpe", _ctx(returns=r))

    assert list(result) == ["sharpe"]
    assert "sharpe" in engine.names
    assert engine.get_metric("sharpe") is engine.metrics["sharpe"]


def test_metric_engine_register_many_accepts_mapping():
    # The test double must inherit BaseMetric to exercise the same public
    # validation as production metrics.
    from app.services.metric.base import BaseMetric

    class _TypedConstantMetric(BaseMetric):
        name = "constant"

        def calculate(self, ctx):
            return 1

    engine = MetricEngine(register_defaults=False, metrics={"alias": _TypedConstantMetric()})
    assert engine.calculate_one("constant", _ctx()) == 1.0
