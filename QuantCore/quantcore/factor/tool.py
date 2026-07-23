"""日期×标的因子宽表的通用横截面预处理函数。

本模块只处理调用方传入的数据，不负责加载行业、市值或其他外部暴露。这样因子
库、自定义因子和组合策略可以共用同一套计算口径。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _require_frame(values: pd.DataFrame, name: str = "values") -> None:
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{name} 必须是 pandas.DataFrame（日期×标的宽表）")


def winsorize(
    values: pd.DataFrame, lower: float = 0.01, upper: float = 0.99
) -> pd.DataFrame:
    """按交易日的横截面分位数截断极值，保留原始缺失值。"""
    _require_frame(values)
    if not 0 <= lower < upper <= 1:
        raise ValueError("winsorize 要求 0 <= lower < upper <= 1")
    low = values.quantile(lower, axis=1)
    high = values.quantile(upper, axis=1)
    return values.clip(lower=low, upper=high, axis=0)


def mad_winsorize(values: pd.DataFrame, n: float = 5.0) -> pd.DataFrame:
    """按交易日使用中位数 ± ``n * 1.4826 * MAD`` 截断极值。

    当某日 MAD 为零时，该日有效值不截断，避免把同质横截面错误改写。
    """
    _require_frame(values)
    if n <= 0:
        raise ValueError("n 必须大于 0")

    median = values.median(axis=1)
    mad = values.sub(median, axis=0).abs().median(axis=1)
    width = mad * 1.4826 * n
    low = median - width
    high = median + width
    result = values.clip(lower=low, upper=high, axis=0)
    zero_mad = width.eq(0)
    if zero_mad.any():
        result.loc[zero_mad] = values.loc[zero_mad]
    return result


def zscore(values: pd.DataFrame) -> pd.DataFrame:
    """按交易日横截面 Z-score 标准化；常数横截面的有效值为 0。"""
    _require_frame(values)
    mean = values.mean(axis=1)
    std = values.std(axis=1, ddof=0)
    result = values.sub(mean, axis=0).div(std.replace(0, np.nan), axis=0)
    constant = std.eq(0)
    if constant.any():
        result.loc[constant] = values.loc[constant].where(
            values.loc[constant].isna(), 0.0
        )
    return result


def rank(values: pd.DataFrame) -> pd.DataFrame:
    """按交易日进行横截面百分位排名。"""
    _require_frame(values)
    return values.rank(axis=1, pct=True, method="average")


def normalize(values: pd.DataFrame) -> pd.DataFrame:
    """按交易日将绝对值和归一化为 1；全零横截面的有效值为 0。"""
    _require_frame(values)
    total = values.abs().sum(axis=1)
    result = values.div(total.replace(0, np.nan), axis=0)
    zero_total = total.eq(0)
    if zero_total.any():
        result.loc[zero_total] = values.loc[zero_total].where(
            values.loc[zero_total].isna(), 0.0
        )
    return result


def _exposure_frame(
    exposure: pd.DataFrame | pd.Series,
    values: pd.DataFrame,
    name: str,
) -> pd.DataFrame:
    if isinstance(exposure, pd.Series):
        return pd.DataFrame(
            np.tile(exposure.reindex(values.columns).to_numpy(), (len(values.index), 1)),
            index=values.index,
            columns=values.columns,
        )
    _require_frame(exposure, name)
    return exposure.reindex(index=values.index, columns=values.columns)


def neutralize(
    values: pd.DataFrame,
    *,
    industry: pd.DataFrame | pd.Series | None = None,
    market_cap: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """按日回归剔除行业和/或对数市值暴露，返回残差。

    ``industry`` 可传日期×标的行业编码，或以标的为索引的静态行业编码 Series；
    ``market_cap`` 必须是日期×标的市值宽表。每个交易日的可用样本不足以估计
    回归时，该日返回缺失值。
    """
    _require_frame(values)
    if industry is None and market_cap is None:
        raise ValueError("neutralize 至少需要 industry 或 market_cap 之一")

    industries = (
        _exposure_frame(industry, values, "industry") if industry is not None else None
    )
    caps = _exposure_frame(market_cap, values, "market_cap") if market_cap is not None else None
    result = pd.DataFrame(np.nan, index=values.index, columns=values.columns, dtype=float)

    for date in values.index:
        y = values.loc[date]
        valid = y.notna()

        if industries is not None:
            labels = industries.loc[date]
            valid &= labels.notna()
        if caps is not None:
            cap = caps.loc[date]
            valid &= cap.notna() & (cap > 0)

        symbols = y.index[valid]
        if symbols.empty:
            continue
        x_parts = [np.ones(len(symbols))]
        if industries is not None:
            dummies = pd.get_dummies(industries.loc[date, symbols], dtype=float)
            # 截距已存在，故省略一个行业以避免完全共线。
            if dummies.shape[1] > 1:
                x_parts.append(dummies.iloc[:, 1:].to_numpy(dtype=float))
        if caps is not None:
            x_parts.append(np.log(caps.loc[date, symbols].to_numpy(dtype=float))[:, None])
        design = np.column_stack(x_parts)
        if len(symbols) <= design.shape[1]:
            continue
        coefficients, _, _, _ = np.linalg.lstsq(design, y.loc[symbols].to_numpy(dtype=float), rcond=None)
        result.loc[date, symbols] = y.loc[symbols].to_numpy(dtype=float) - design @ coefficients
    return result


__all__ = [
    "mad_winsorize",
    "neutralize",
    "normalize",
    "rank",
    "winsorize",
    "zscore",
]
