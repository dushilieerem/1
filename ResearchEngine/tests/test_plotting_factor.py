"""分层 / 多空 / 行业 / 归因 出图 smoke 测试。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.services.factor.layered import layered_equity, layered_returns
from app.services.factor.plotting import (
    plot_equity_drawdown,
    plot_ff3_attribution,
    plot_industry_ic_ir,
    plot_layered_equity,
    plot_long_short,
)


def _equity(periods=60, seed=0):
    dates = pd.bdate_range("2020-01-03", periods=periods)
    rng = np.random.default_rng(seed)
    r = pd.Series(rng.normal(0, 0.01, periods), index=dates)
    return 1.0 + r.cumsum()


# ---------------- 累计收益 + 基准 ----------------

def test_equity_drawdown_with_benchmark(tmp_path):
    eq = _equity(seed=0)
    bench = _equity(seed=1)
    png = plot_equity_drawdown(
        eq, tmp_path / "ed.png", show_yearly_table=False, benchmark=bench
    )
    assert png and Path(png).exists()


# ---------------- 分层回测 ----------------

def test_layered_equity(tmp_path):
    dates = pd.bdate_range("2020-01-03", periods=40)
    syms = [f"S{i}" for i in range(10)]
    rng = np.random.default_rng(1)
    fv = pd.DataFrame(rng.normal(0, 1, (40, 10)), index=dates, columns=syms)
    close = pd.DataFrame(100.0, index=dates, columns=syms)
    for i in range(1, 40):
        close.iloc[i] = close.iloc[i - 1] * (1 + rng.normal(0, 0.01, 10))
    le = layered_equity(layered_returns(fv, close, n_groups=5, rebalance="monthly"))
    png = plot_layered_equity(le, tmp_path / "layered.png")
    assert png and Path(png).exists()
    # 叠基准
    png2 = plot_layered_equity(le, tmp_path / "layered_b.png", benchmark=_equity(40))
    assert png2 and Path(png2).exists()


def test_layered_equity_empty(tmp_path):
    assert plot_layered_equity(pd.DataFrame(), tmp_path / "none.png") is None


# ---------------- 多空 ----------------

def test_long_short(tmp_path):
    png = plot_long_short(_equity(), tmp_path / "ls.png")
    assert png and Path(png).exists()
    assert plot_long_short(pd.Series(dtype=float), tmp_path / "none.png") is None


# ---------------- 分行业 IC/IR ----------------

def test_industry_ic_ir_plot(tmp_path):
    df = pd.DataFrame([
        {"industry": "银行", "ic": 0.05, "ir": 0.4, "n_obs": 100},
        {"industry": "地产", "ic": -0.03, "ir": -0.2, "n_obs": 100},
        {"industry": "医药", "ic": 0.02, "ir": 0.15, "n_obs": 100},
    ])
    png = plot_industry_ic_ir(df, tmp_path / "ind.png")
    assert png and Path(png).exists()
    assert plot_industry_ic_ir(pd.DataFrame(), tmp_path / "none.png") is None


# ---------------- 三因子归因 ----------------

def test_ff3_attribution_plot(tmp_path):
    reg = {
        "alpha": 0.05, "beta_mkt": 0.6, "beta_smb": 0.3, "beta_hml": 0.2,
        "t_alpha": 2.0, "t_beta_mkt": 5.0, "t_beta_smb": 3.0, "t_beta_hml": 2.0,
        "r_squared": 0.75, "n_obs": 500,
    }
    png = plot_ff3_attribution(reg, tmp_path / "ff3.png")
    assert png and Path(png).exists()
    # 无效结果
    assert plot_ff3_attribution(
        {"n_obs": 0, "alpha": float("nan")}, tmp_path / "none.png"
    ) is None
