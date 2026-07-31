"""因子模型与归因 - FF3 因子构造 + 时序回归 + 分行业 IC/IR。

三因子（Fama-French 口径，自构造）：

- **MKT** = 市值加权全市场日收益（同时作累计收益图的基准）。
- **SMB** = 小市值组 − 大市值组多空日收益（按 ``total_mv`` 分 N 组，Q1 小盘 − QN 大盘）。
- **HML** = 高账面市值比组 − 低账面市值比组多空（按 ``1/pb`` 分组，高 1/pb=价值股 − 低 1/pb=成长股）。

SMB/HML 复用 :mod:`researchengine.layered`，与分层回测同口径。

归因：因子多空组合日收益对 MKT+SMB+HML 做 OLS 时序回归，得 alpha（年化）与各因子
beta（因子暴露）。OLS 手算（``numpy.linalg``），不引入 statsmodels。
"""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
import pandas as pd

from quantcore.backtest.adapter.calendar import PandasCalendar
from researchengine.layered import layered_returns, long_short_returns

#: 年化周期数（与指标层默认一致）
_PERIODS_PER_YEAR = 252


def market_weighted_returns(
    close: pd.DataFrame,
    total_mv: pd.DataFrame,
    rebalance: str = "monthly",
) -> pd.Series:
    """市值加权全市场日收益（MKT / 基准）。

    每个调仓日按 ``total_mv`` 归一化得权重，``t+1`` 收盘建仓并作为净值起点，
    ``t+2`` 起持有；口径与 :class:`NativeEngine` 一致（固定本金）。

    Parameters
    ----------
    close, total_mv : pd.DataFrame
        ``日期×标的`` 收盘价 / 总市值。
    rebalance : str
        调仓频率（默认 monthly）。

    Returns
    -------
    pd.Series
        全市场市值加权日收益（首日已剔除）。
    """
    common_dates = close.index.intersection(total_mv.index)
    common_symbols = close.columns.intersection(total_mv.columns)
    if common_dates.empty or common_symbols.empty:
        return pd.Series(dtype=float)
    close = close.loc[common_dates, common_symbols]
    mv = total_mv.loc[common_dates, common_symbols]

    reb_np = PandasCalendar().rebalance_mask(close.index, rebalance).to_numpy()[:, None]
    ret = close.pct_change()

    # 市值权重 = mv / 当日总市值（调仓日计算，区间 ffill）
    mv_np = mv.to_numpy(dtype=float)
    mv_sum = np.nansum(mv_np, axis=1, keepdims=True)
    safe_sum = np.where(mv_sum > 0, mv_sum, 1.0)
    weight = np.where(mv_sum > 0, mv_np / safe_sum, np.nan)
    weight = np.where(reb_np, weight, np.nan)
    executed = pd.DataFrame(weight, index=close.index, columns=close.columns).ffill().shift(1).fillna(0.0)
    held = executed.shift(1).fillna(0.0)
    port_ret = (held * ret).sum(axis=1)
    return port_ret.iloc[1:].dropna()


def ff3_factors(
    close: pd.DataFrame,
    total_mv: pd.DataFrame,
    pb: pd.DataFrame,
    rebalance: str = "monthly",
    n_groups: int = 5,
) -> pd.DataFrame:
    """构造 FF3 因子日收益 DataFrame。

    Parameters
    ----------
    close, total_mv, pb : pd.DataFrame
        ``日期×标的`` 收盘价 / 总市值 / 市净率。``pb`` 用于算 ``1/pb``（账面市值比）。
    rebalance : str
        调仓频率。
    n_groups : int
        分组数（默认 5，经典 FF3 用 5 组）。

    Returns
    -------
    pd.DataFrame
        三列 ``[MKT, SMB, HML]``，按日期对齐并 dropna。

    Notes
    -----
    - SMB = 小盘(Q1) − 大盘(QN)：按 ``total_mv`` 分组，做多低市值组、做空高市值组。
    - HML = 价值(QN) − 成长(Q1)：按 ``1/pb`` 分组，做多高账面市值比（低 PB）组、
      做空低账面市值比（高 PB）组。``pb<=0`` 视作无效（``1/pb`` 置 NaN）。
    """
    mkt = market_weighted_returns(close, total_mv, rebalance)

    # SMB: 小盘 - 大盘 = Q1 - QN
    smb_lr = layered_returns(total_mv, close, n_groups=n_groups, rebalance=rebalance)
    smb = long_short_returns(smb_lr, q_high=1, q_low=n_groups)

    # HML: 价值(高 1/pb) - 成长(低 1/pb) = QN - Q1
    bm = 1.0 / pb.where(pb > 0)  # 账面市值比；pb<=0 -> NaN
    hml_lr = layered_returns(bm, close, n_groups=n_groups, rebalance=rebalance)
    hml = long_short_returns(hml_lr, q_high=n_groups, q_low=1)

    df = pd.DataFrame({"MKT": mkt, "SMB": smb, "HML": hml})
    return df.dropna()


def ff3_regression(
    portfolio_returns: pd.Series,
    ff3: pd.DataFrame,
    periods_per_year: int = _PERIODS_PER_YEAR,
) -> dict:
    """因子多空组合收益对 FF3 做 OLS 时序回归，算因子暴露。

        ret_t = α + β_mkt·MKT_t + β_smb·SMB_t + β_hml·HML_t + ε_t

    Parameters
    ----------
    portfolio_returns : pd.Series
        被解释的日收益（通常为因子多空组合收益）。
    ff3 : pd.DataFrame
        :func:`ff3_factors` 的输出（含 MKT/SMB/HML）。
    periods_per_year : int
        年化周期数（alpha 日收益 × 此值 -> 年化）。

    Returns
    -------
    dict
        ``alpha``(年化)、``beta_mkt/beta_smb/beta_hml``、
        ``t_alpha/t_beta_*``、``r_squared``、``n_obs``；样本不足返回 NaN。
    """
    nan_result = {
        "alpha": np.nan, "beta_mkt": np.nan, "beta_smb": np.nan, "beta_hml": np.nan,
        "t_alpha": np.nan, "t_beta_mkt": np.nan, "t_beta_smb": np.nan, "t_beta_hml": np.nan,
        "r_squared": np.nan, "n_obs": 0,
    }
    df = pd.DataFrame({"y": portfolio_returns}).join(ff3, how="inner").dropna()
    n = len(df)
    if n < 10:
        return nan_result

    X = np.column_stack([np.ones(n), df["MKT"].to_numpy(), df["SMB"].to_numpy(), df["HML"].to_numpy()])
    y = df["y"].to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    k = X.shape[1]
    dof = n - k
    sigma2 = float(resid @ resid) / dof if dof > 0 else np.nan
    XtX_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(XtX_inv) * sigma2)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = beta / se
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else np.nan

    return {
        "alpha": beta[0] * periods_per_year,
        "beta_mkt": beta[1],
        "beta_smb": beta[2],
        "beta_hml": beta[3],
        "t_alpha": t[0],
        "t_beta_mkt": t[1],
        "t_beta_smb": t[2],
        "t_beta_hml": t[3],
        "r_squared": r2,
        "n_obs": n,
    }


def industry_ic_ir(
    factor_values: pd.DataFrame,
    forward_returns: pd.DataFrame,
    industry_map: Union[pd.Series, dict],
    method: str = "pearson",
    min_obs: int = 10,
) -> pd.DataFrame:
    """分行业 IC / IR。

    Parameters
    ----------
    factor_values, forward_returns : pd.DataFrame
        ``日期×标的`` 因子值 / 远期收益。
    industry_map : pd.Series or dict
        ``标的 -> 行业`` 映射（来自 ``stock_info``）。
    method : str
        ``"pearson"``（IC，默认）或 ``"rank"``（RankIC）。
    min_obs : int
        有效 IC 日数下限（不足返回该行业为空）。

    Returns
    -------
    pd.DataFrame
        列 ``[industry, ic, ir, n_obs]``，按 IC 降序。``ir = ic均值 / ic标准差``。
    """
    ind_series = pd.Series(industry_map)
    common_symbols = factor_values.columns.intersection(forward_returns.columns)
    fv = factor_values[common_symbols]
    fr = forward_returns[common_symbols]

    rows = []
    for ind in ind_series.dropna().unique():
        syms = ind_series[ind_series == ind].index.intersection(common_symbols)
        if len(syms) < 2:
            continue
        fv_i, fr_i = fv[syms], fr[syms]
        if method == "rank":
            fv_i = fv_i.rank(axis=1)
            fr_i = fr_i.rank(axis=1)
        ic_series = fv_i.corrwith(fr_i, axis=1).dropna()
        if len(ic_series) < min_obs:
            continue
        std = ic_series.std()
        rows.append({
            "industry": ind,
            "ic": float(ic_series.mean()),
            "ir": float(ic_series.mean() / std) if std > 0 else np.nan,
            "n_obs": int(len(ic_series)),
        })
    if not rows:
        return pd.DataFrame(columns=["industry", "ic", "ir", "n_obs"])
    return pd.DataFrame(rows).sort_values("ic", ascending=False).reset_index(drop=True)
