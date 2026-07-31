"""回测适配层测试：接口、策略、NativeEngine 与注册表。"""

import numpy as np
import pandas as pd
import pytest

from quantcore import BacktestResult
from quantcore.backtest.adapter import (
    BacktestConfig,
    BacktestSignals,
    FactorGroupStrategy,
    FactorQuantileStrategy,
    IBacktestEngine,
    IStrategy,
    NativeEngine,
    PandasCalendar,
    get_backtest_engine,
)


# ---------------- 固件 ----------------

def _make_panel(n_dates=10, n_sym=20, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n_dates)
    symbols = [f"S{i:03d}" for i in range(n_sym)]
    fv = pd.DataFrame(rng.normal(0, 1, (n_dates, n_sym)), index=dates, columns=symbols)
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, (n_dates, n_sym)), axis=0)),
        index=dates, columns=symbols,
    )
    return fv, close


# ---------------- BacktestConfig ----------------

def test_backtest_config_defaults():
    cfg = BacktestConfig()
    assert cfg.engine == "native"
    assert cfg.commission_rate == 0.0
    assert cfg.slippage_rate == 0.0
    assert cfg.stamp_tax == 0.0
    assert cfg.periods_per_year == 252


# ---------------- BacktestResult 扩展 ----------------

def test_backtest_result_returns_derived_from_equity():
    eq = pd.Series([1.0, 1.1, 1.05], index=pd.bdate_range("2022-01-03", periods=3))
    res = BacktestResult(equity_curve=eq)
    # 未显式给 returns -> 由 equity 派生
    assert len(res.returns) == 2
    assert res.positions is None
    assert res.portfolio is None


# ---------------- FactorQuantileStrategy ----------------

def test_factor_quantile_strategy_long_short():
    fv, close = _make_panel()
    strat = FactorQuantileStrategy(
        fv, close, rebalance="daily", stock_num=5, long_short=True
    )
    assert isinstance(strat, IStrategy)
    sig = strat.generate_signals()
    assert isinstance(sig, BacktestSignals)
    tw = sig.target_weights
    assert tw.shape == fv.shape
    # 每个调仓日权重和 ≈ 0（多空对冲）
    assert (tw.sum(axis=1).abs() < 1e-9).all()
    assert (tw.abs() <= 1.0).all().all()
    # 单边 5 -> 非零不超过 2*5
    assert (tw.abs().gt(0).sum(axis=1) <= 2 * 5).all()


def test_factor_quantile_strategy_long_only():
    fv, close = _make_panel()
    strat = FactorQuantileStrategy(
        fv, close, rebalance="daily", stock_num=5, long_short=False
    )
    tw = strat.generate_signals().target_weights
    assert (tw.sum(axis=1) - 1.0).abs().max() < 1e-9
    assert (tw >= 0).all().all()
    assert (tw.gt(0).sum(axis=1) == 5).all()


def test_factor_quantile_strategy_all_equal_factor_breaks_ties_by_column_order():
    """全相等因子按列顺序稳定选出 Top-N。"""
    fv, close = _make_panel()
    fv.loc[:, :] = 0.0
    weights = FactorQuantileStrategy(
        fv, close, rebalance="daily", stock_num=5, long_short=False
    ).generate_signals().target_weights
    assert weights.iloc[:, :5].eq(0.2).all().all()
    assert weights.iloc[:, 5:].eq(0.0).all().all()


# ---------------- PandasCalendar ----------------

def test_calendar_rebalance_mask():
    cal = PandasCalendar()
    idx = pd.bdate_range("2022-01-03", periods=30)
    for freq in ("daily", "weekly", "monthly"):
        mask = cal.rebalance_mask(idx, freq)
        assert mask.dtype == bool
        assert mask.iloc[0]  # 首日必为调仓日


def test_calendar_custom_rebalance_days():
    idx = pd.bdate_range("2022-01-03", periods=35)
    mask = PandasCalendar().rebalance_mask(idx, 15)
    assert list(np.flatnonzero(mask.to_numpy())) == [0, 15, 30]


def test_factor_group_strategy_uses_top_group():
    fv, close = _make_panel(n_dates=10, n_sym=20)
    signals = FactorGroupStrategy(
        fv, close, groups=4, rebalance_days=3, long_short=False
    ).generate_signals()
    weights = signals.target_weights
    assert (weights.iloc[[0, 3, 6, 9]].sum(axis=1) - 1.0).abs().max() < 1e-9
    assert weights.iloc[1].isna().all()


def test_factor_group_strategy_all_equal_factor_breaks_ties_by_column_order():
    """全相等因子按列顺序稳定分配最高组与最低组。"""
    fv, close = _make_panel(n_dates=10, n_sym=20)
    fv.loc[:, :] = 0.0
    signals = FactorGroupStrategy(
        fv, close, groups=2, rebalance_days=3, long_short=True
    ).generate_signals()
    weights = signals.target_weights
    rebalance_weights = weights.iloc[[0, 3, 6, 9]]
    assert rebalance_weights.iloc[:, :10].eq(-0.1).all().all()
    assert rebalance_weights.iloc[:, 10:].eq(0.1).all().all()


# ---------------- NativeEngine ----------------

def test_native_engine_run_shapes():
    fv, close = _make_panel(n_dates=10, n_sym=20)
    sig = FactorQuantileStrategy(fv, close, rebalance="daily", stock_num=5).generate_signals()
    res = NativeEngine().run(sig, BacktestConfig())
    assert isinstance(res, BacktestResult)
    assert len(res.equity_curve) == len(res.returns)
    assert res.positions.shape[1] == 20
    # 第二个交易日收盘完成建仓，作为净值 1.0 的共同起点。
    assert res.equity_curve.iloc[0] == pytest.approx(1.0)
    assert res.returns.iloc[0] == pytest.approx(0.0)


def test_native_engine_starts_return_after_close_build_date():
    dates = pd.bdate_range("2024-01-02", periods=4)
    close = pd.DataFrame({"A": [100.0, 110.0, 121.0, 133.1]}, index=dates)
    target = pd.DataFrame({"A": [1.0, float("nan"), float("nan"), float("nan")]}, index=dates)

    result = NativeEngine().run(BacktestSignals(target_weights=target, close=close), BacktestConfig())

    assert result.returns.index.tolist() == dates[1:].tolist()
    assert result.returns.tolist() == pytest.approx([0.0, 0.1, 0.1])
    assert result.equity_curve.tolist() == pytest.approx([1.0, 1.1, 1.2])
    assert result.positions.loc[dates[1], "A"] == pytest.approx(1.0)


def test_native_engine_records_rebalance_logs():
    index = pd.bdate_range("2024-01-02", periods=3)
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0], "B": [10.0, 10.0, 10.0]}, index=index)
    target = pd.DataFrame({"A": [0.5, float("nan"), 0.0], "B": [0.5, float("nan"), 1.0]}, index=index)

    result = NativeEngine().run(BacktestSignals(target_weights=target, close=close), BacktestConfig())

    assert result.rebalance_logs is not None
    assert result.rebalance_logs.loc[index[0], "side"].tolist() == ["buy", "buy"]
    assert result.rebalance_logs.loc[index[2], "side"].tolist() == ["sell", "buy"]


def test_native_engine_only_charges_stamp_tax_on_sells():
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    close = pd.DataFrame({"A": [100.0, 100.0, 100.0, 100.0]}, index=dates)
    target = pd.DataFrame({"A": [1.0, 0.0, 0.0, 0.0]}, index=dates)
    signals = BacktestSignals(target_weights=target, close=close)

    result = NativeEngine().run(signals, BacktestConfig(stamp_tax=0.001))

    assert result.returns.iloc[-1] == pytest.approx(-0.001)


def test_native_engine_parity_with_build_factor_portfolio():
    """NativeEngine + FactorQuantileStrategy 与 build_factor_portfolio（薄包装）逐位相等。"""
    from researchengine.portfolio import build_factor_portfolio

    fv, close = _make_panel(n_dates=15, n_sym=25, seed=7)
    sig = FactorQuantileStrategy(
        fv, close, rebalance="weekly", stock_num=4, long_short=True
    ).generate_signals()
    res = NativeEngine().run(sig, BacktestConfig())
    eq2, ret2, pos2 = build_factor_portfolio(
        fv, close, rebalance="weekly", stock_num=4, long_short=True
    )
    pd.testing.assert_series_equal(res.equity_curve, eq2)
    pd.testing.assert_series_equal(res.returns, ret2)
    pd.testing.assert_frame_equal(res.positions, pos2)


# ---------------- 注册表 ----------------

def test_registry_native():
    eng = get_backtest_engine("native")
    assert isinstance(eng, IBacktestEngine)
    assert isinstance(eng, NativeEngine)


def test_registry_unknown_raises():
    with pytest.raises(ValueError):
        get_backtest_engine("nonsense")


def test_registry_rejects_removed_vectorbt_backend():
    with pytest.raises(ValueError, match="未知回测后端"):
        get_backtest_engine("vectorbt")
