"""因子模型与归因测试。

- FF3 构造：MKT 数值、SMB/HML 方向（小盘涨大盘跌 -> SMB 正；价值涨成长跌 -> HML 正）
- 回归反解：合成 ret = α + β·ff3 + ε，反推 alpha/beta 接近真值
- 行业 IC/IR：强相关行业 IC > 弱相关行业
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.factor.riskmodel import (
    ff3_factors,
    ff3_regression,
    industry_ic_ir,
    market_weighted_returns,
)


# ---------------- MKT ----------------

def test_market_weighted_equal_cap():
    """等市值 + 全市场日涨1% -> MKT ≈ 0.01/日。"""
    dates = pd.bdate_range("2022-01-03", periods=10)
    syms = [f"S{i}" for i in range(10)]
    close = pd.DataFrame(100.0, index=dates, columns=syms, dtype=float)
    for i in range(1, 10):
        close.iloc[i] = close.iloc[i - 1] * 1.01
    mv = pd.DataFrame(1.0, index=dates, columns=syms)  # 等市值 -> 等权
    mkt = market_weighted_returns(close, mv, rebalance="monthly")
    assert len(mkt) == 9  # 去首日
    assert mkt.iloc[0] == pytest.approx(0.0)
    assert (abs(mkt.iloc[1:] - 0.01) < 1e-9).all()


def test_market_weighted_cap_weighted():
    """市值加权：大市值标的涨 -> MKT 偏向其收益。"""
    dates = pd.bdate_range("2022-01-03", periods=5)
    syms = ["A", "B"]
    close = pd.DataFrame(100.0, index=dates, columns=syms, dtype=float)
    close.iloc[2:, 0] = 101.0  # A 平稳
    close.iloc[2:, 1] = 110.0  # B 涨（B 是大市值）
    mv = pd.DataFrame({"A": 10.0, "B": 1000.0}, index=dates)  # B 市值远大
    mkt = market_weighted_returns(close, mv, rebalance="monthly")
    # B 权重 ≈ 0.99，收益 ≈ 0.1/日（100->110）；MKT 应接近 B 的收益
    assert mkt.iloc[1] > 0.05


# ---------------- FF3 因子构造 ----------------

def _ff3_scenario(periods=10, n=10):
    """构造：S0-S4 小市值+低PB(价值)，涨；S5-S9 大市值+高PB(成长)，跌。"""
    dates = pd.bdate_range("2022-01-03", periods=periods)
    syms = [f"S{i}" for i in range(n)]
    close = pd.DataFrame(100.0, index=dates, columns=syms, dtype=float)
    for i in range(1, periods):
        close.iloc[i, :5] = close.iloc[i - 1, :5] * 1.02   # 价值/小盘 涨2%
        close.iloc[i, 5:] = close.iloc[i - 1, 5:] * 0.98  # 成长/大盘 跌2%
    mv = pd.DataFrame(1.0, index=dates, columns=syms)
    mv.iloc[:, :5] = 1.0     # 小盘
    mv.iloc[:, 5:] = 100.0   # 大盘
    pb = pd.DataFrame(1.0, index=dates, columns=syms)
    pb.iloc[:, :5] = 1.0     # 低PB(价值)
    pb.iloc[:, 5:] = 10.0    # 高PB(成长)
    return close, mv, pb


def test_ff3_factors_columns():
    close, mv, pb = _ff3_scenario()
    ff3 = ff3_factors(close, mv, pb, n_groups=2)
    assert list(ff3.columns) == ["MKT", "SMB", "HML"]
    assert len(ff3) > 0


def test_ff3_smb_direction():
    """小盘涨、大盘跌 -> SMB = 小盘 - 大盘 > 0。"""
    close, mv, pb = _ff3_scenario()
    ff3 = ff3_factors(close, mv, pb, n_groups=2)
    assert ff3["SMB"].iloc[1] > 0.01  # 建仓日后显著为正


def test_ff3_hml_direction():
    """价值(低PB)涨、成长(高PB)跌 -> HML = 价值 - 成长 > 0。"""
    close, mv, pb = _ff3_scenario()
    ff3 = ff3_factors(close, mv, pb, n_groups=2)
    assert ff3["HML"].iloc[1] > 0.01


def test_ff3_mkt_sign():
    """大市值权重大 + 大盘跌 -> MKT 应为负（市值加权偏向大盘）。"""
    close, mv, pb = _ff3_scenario()
    ff3 = ff3_factors(close, mv, pb, n_groups=2)
    assert ff3["MKT"].iloc[1] < 0  # 大盘权重大且跌


# ---------------- 三因子回归 ----------------

def test_ff3_regression_recovery():
    """合成 ret = α + β·ff3 + ε，反解 alpha/beta 接近真值。"""
    rng = np.random.default_rng(42)
    n = 500
    dates = pd.bdate_range("2020-01-03", periods=n)
    mkt = pd.Series(rng.normal(0, 0.01, n), index=dates)
    smb = pd.Series(rng.normal(0, 0.01, n), index=dates)
    hml = pd.Series(rng.normal(0, 0.01, n), index=dates)
    true_alpha_day = 0.0005
    true_beta = np.array([0.6, 0.3, 0.2])
    y = (
        true_alpha_day
        + true_beta[0] * mkt
        + true_beta[1] * smb
        + true_beta[2] * hml
        + pd.Series(rng.normal(0, 0.001, n), index=dates)
    )
    ff3 = pd.DataFrame({"MKT": mkt, "SMB": smb, "HML": hml})
    res = ff3_regression(y, ff3)
    assert res["n_obs"] == n
    # alpha 年化 = 0.0005 * 252 ≈ 0.126
    assert abs(res["alpha"] - true_alpha_day * 252) < 0.05
    assert abs(res["beta_mkt"] - true_beta[0]) < 0.05
    assert abs(res["beta_smb"] - true_beta[1]) < 0.05
    assert abs(res["beta_hml"] - true_beta[2]) < 0.05
    assert res["r_squared"] > 0.9
    # t 值应较大
    assert abs(res["t_beta_mkt"]) > 5


def test_ff3_regression_insufficient():
    """样本不足 -> 返回 NaN。"""
    ff3 = pd.DataFrame({
        "MKT": [0.01, 0.02], "SMB": [0.0, 0.01], "HML": [0.0, 0.0],
    }, index=pd.bdate_range("2022-01-03", periods=2))
    res = ff3_regression(pd.Series([0.01, 0.02], index=ff3.index), ff3)
    assert np.isnan(res["alpha"])
    assert res["n_obs"] == 0


# ---------------- 行业 IC/IR ----------------

def test_industry_ic_ir_direction():
    """行业 A 因子强正相关（IC 高），行业 B 弱相关（IC 低）。"""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2022-01-03", periods=60)
    syms = [f"S{i}" for i in range(10)]
    fv = pd.DataFrame(rng.normal(0, 1, (60, 10)), index=dates, columns=syms)
    fr = pd.DataFrame(0.0, index=dates, columns=syms, dtype=float)
    # 行业 A（S0-S4）：因子值强正相关收益
    fr.iloc[:, :5] = fv.iloc[:, :5] * 0.8 + rng.normal(0, 0.3, (60, 5))
    # 行业 B（S5-S9）：纯噪声
    fr.iloc[:, 5:] = rng.normal(0, 1, (60, 5))
    ind_map = {**{f"S{i}": "A" for i in range(5)}, **{f"S{i}": "B" for i in range(5, 10)}}
    res = industry_ic_ir(fv, fr, ind_map)
    assert len(res) == 2
    ic_a = res.loc[res["industry"] == "A", "ic"].iloc[0]
    ic_b = res.loc[res["industry"] == "B", "ic"].iloc[0]
    assert ic_a > 0.3  # A 强正相关
    assert abs(ic_b) < 0.3  # B 弱
    assert ic_a > ic_b


def test_industry_ic_ir_rank_method():
    """rank 口径也能算。"""
    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2022-01-03", periods=40)
    syms = [f"S{i}" for i in range(8)]
    fv = pd.DataFrame(rng.normal(0, 1, (40, 8)), index=dates, columns=syms)
    fr = fv * 0.5 + rng.normal(0, 1, (40, 8))
    ind_map = {**{f"S{i}": "X" for i in range(4)}, **{f"S{i}": "Y" for i in range(4, 8)}}
    res = industry_ic_ir(fv, fr, ind_map, method="rank")
    assert len(res) == 2
    assert res["ic"].notna().all()


def test_industry_ic_ir_empty():
    """空数据 -> 空 DataFrame。"""
    res = industry_ic_ir(
        pd.DataFrame(dtype=float), pd.DataFrame(dtype=float), {}
    )
    assert res.empty
