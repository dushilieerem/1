"""分层回测底座测试。

首日信号、首个持有日收益、后续收盘到收盘收益、组内等权。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from researchengine.layered import (
    layered_equity,
    layered_returns,
    long_short_returns,
    quantile_groups,
)


# ---------------- 分组 ----------------

def test_quantile_groups_basic():
    """10 标的因子值 1..10，分 2 组：高 5 个 -> Q1，低 5 个 -> Q2。"""
    dates = pd.bdate_range("2022-01-03", periods=3)
    syms = [f"S{i}" for i in range(10)]
    fv = pd.DataFrame(
        np.tile(np.arange(1, 11), (3, 1)), index=dates, columns=syms
    )
    g = quantile_groups(fv, n_groups=2)
    # 每行：S0-S4(值1-5)->Q2，S5-S9(值6-10)->Q1
    for i in range(3):
        assert (g.iloc[i, :5] == 2).all()
        assert (g.iloc[i, 5:] == 1).all()


def test_quantile_groups_nan_preserved():
    """原 NaN 标的组号为 NA，不参与分组。"""
    fv = pd.DataFrame(
        [[1.0, 2.0, np.nan, 4.0, 5.0]],
        index=pd.bdate_range("2022-01-03", periods=1),
        columns=list("ABCDE"),
    )
    g = quantile_groups(fv, n_groups=2)
    assert pd.isna(g.iloc[0, 2])  # C 为 NaN
    # 其余 4 只分到 Q1/Q2
    valid = g.iloc[0].dropna()
    assert set(valid) == {1, 2}


def test_quantile_groups_uses_raw_value_qcut_at_duplicate_boundaries():
    """重复边界按 qcut 的原始值归属，不强行按 rank 拆开。"""
    values = [0.0, 0.0, 0.0, 1.0, 2.0, 3.0]
    fv = pd.DataFrame([values], columns=list("ABCDEF"))
    groups = quantile_groups(fv, n_groups=3).iloc[0].tolist()
    expected = (
        3 - pd.qcut(pd.Series(values), 3, labels=False, duplicates="drop")
    ).tolist()
    assert groups == expected


def test_quantile_groups_insufficient_no_error():
    """有效标的数 < n_groups 时不报错（降级，多 rank 落同组）。"""
    fv = pd.DataFrame(
        [[1.0, 2.0]], index=pd.bdate_range("2022-01-03", periods=1), columns=["A", "B"]
    )
    g = quantile_groups(fv, n_groups=5)  # 不抛异常
    assert g.shape == (1, 2)
    assert g.notna().all().all()


def test_quantile_groups_all_equal_breaks_ties_by_column_order():
    """所有有效因子值相同时，按列顺序稳定地打破并列。"""
    fv = pd.DataFrame(
        [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
        index=pd.bdate_range("2022-01-03", periods=2),
        columns=["A", "B", "C"],
    )
    groups = quantile_groups(fv, n_groups=3)
    assert groups.iloc[0].tolist() == [3, 2, 1]
    assert groups.iloc[1].tolist() == [3, 2, 1]


def test_quantile_groups_invalid_n():
    with pytest.raises(ValueError):
        quantile_groups(pd.DataFrame([[1.0]]), n_groups=1)


# ---------------- 分层收益 / 净值口径 ----------------

def _make_panel(periods=10, n=10):
    """构造确定性面板：S0-S4 每日涨1%，S5-S9 每日涨2%，因子值恒定 1..10。"""
    dates = pd.bdate_range("2022-01-03", periods=periods)
    syms = [f"S{i}" for i in range(n)]
    close = pd.DataFrame(100.0, index=dates, columns=syms)
    for i in range(1, periods):
        close.iloc[i, :5] = close.iloc[i - 1, :5] * 1.01
        close.iloc[i, 5:] = close.iloc[i - 1, 5:] * 1.02
    fv = pd.DataFrame(np.tile(np.arange(1, n + 1), (periods, 1)), index=dates, columns=syms)
    return fv, close


def test_layered_returns_equal_weight():
    """首个保留日包含首个持有收益，之后 Q1/Q2 分别按 2%/1% 计算。"""
    fv, close = _make_panel()
    lr = layered_returns(fv, close, n_groups=2, rebalance="monthly")
    assert (abs(lr["Q1"] - 0.02) < 1e-12).all()
    assert (abs(lr["Q2"] - 0.01) < 1e-12).all()


def test_layered_returns_reuses_precomputed_group_assignments():
    """传入预计算组号时，分层收益与内部计算逐位一致。"""
    fv, close = _make_panel()
    assignments = quantile_groups(fv, n_groups=2)
    expected = layered_returns(fv, close, n_groups=2, rebalance="monthly")
    actual = layered_returns(
        fv,
        close,
        n_groups=2,
        rebalance="monthly",
        group_assignments=assignments,
    )

    pd.testing.assert_frame_equal(actual, expected)


def test_layered_equity_cumsum():
    """累计净值按日收益复利计算。"""
    fv, close = _make_panel(periods=10)
    lr = layered_returns(fv, close, n_groups=2, rebalance="monthly")
    le = layered_equity(lr)
    # 展示曲线首日归一，后续 8 个收益日复利。
    assert abs(le["Q1"].iloc[-1] - 1.02 ** 8) < 1e-9
    assert abs(le["Q2"].iloc[-1] - 1.01 ** 8) < 1e-9
    assert abs(le["Q1"].iloc[0] - 1.0) < 1e-9


def test_layered_rebalance_daily():
    """daily 调仓：每日重新分组，但因子恒定时收益与 monthly 一致。"""
    fv, close = _make_panel()
    lr_m = layered_returns(fv, close, n_groups=2, rebalance="monthly")
    lr_d = layered_returns(fv, close, n_groups=2, rebalance="daily")
    # 因子恒定 -> 分组不变 -> 收益逐位相等。
    pd.testing.assert_series_equal(lr_m["Q1"], lr_d["Q1"])


def test_long_short_returns():
    """多空 = Q1 - Q2 = 0.02 - 0.01 = 0.01/日。"""
    fv, close = _make_panel()
    lr = layered_returns(fv, close, n_groups=2, rebalance="monthly")
    ls = long_short_returns(lr)  # 默认 Q1 - QN = Q1 - Q2
    assert (abs(ls - 0.01) < 1e-12).all()
    # 显式指定
    ls2 = long_short_returns(lr, q_low=2, q_high=1)
    pd.testing.assert_series_equal(ls, ls2)


def test_long_short_custom_groups():
    """5 组多空：Q1 - Q5。"""
    fv, close = _make_panel(n=10)
    lr = layered_returns(fv, close, n_groups=5, rebalance="monthly")
    ls = long_short_returns(lr)
    assert ls.name is None or "Q" not in str(ls.name)
    # Q1(高因子值,涨2%) - Q5(低因子值,涨1%) ≈ 0.01
    assert abs(ls.iloc[0] - 0.01) < 1e-9


# ---------------- 边界 / 降级 ----------------

def test_empty_data():
    assert quantile_groups(pd.DataFrame(dtype=float), 5).empty
    assert layered_returns(pd.DataFrame(dtype=float), pd.DataFrame(dtype=float)).empty


def test_layered_returns_nan_factor():
    """因子值含 NaN：当日无效标的不参与分组，组收益仍正确。"""
    fv, close = _make_panel(periods=5, n=10)
    fv.iloc[0, 0] = np.nan  # S0 首日 NaN
    lr = layered_returns(fv, close, n_groups=2, rebalance="monthly")
    # 两组时 qcut 的低值组为 Q2，含一只 2% 标的，等权收益为 1.2%。
    assert abs(lr["Q2"].iloc[0] - 0.012) < 1e-9
    assert abs(lr["Q2"].iloc[1] - 0.012) < 1e-9


def test_layered_returns_all_equal_factor_breaks_ties_by_column_order():
    """全相等因子仍按列顺序分组，保持各层收益曲线连续。"""
    fv, close = _make_panel(periods=5, n=10)
    fv.loc[:, :] = 0.0
    returns = layered_returns(fv, close, n_groups=2, rebalance="daily")
    assert returns.iloc[0].tolist() == pytest.approx([0.02, 0.01])
    assert (returns["Q1"] - 0.02).abs().lt(1e-12).all()
    assert (returns["Q2"] - 0.01).abs().lt(1e-12).all()


def test_long_short_missing_column():
    fv, close = _make_panel()
    lr = layered_returns(fv, close, n_groups=2, rebalance="monthly")
    with pytest.raises(KeyError):
        long_short_returns(lr, q_high=99)
