"""Alpha158 / Alpha360 特征库。

因子名使用 ``alpha158_`` 或 ``alpha360_`` 前缀，后接特征名的小写形式，例如
``alpha158_kmid``。
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from app.quantcore import FactorLibrary


EPSILON = 1e-12
ROLLING_WINDOWS = (5, 10, 20, 30, 60)


def _rolling_apply(frame: pd.DataFrame, window: int, func: Callable) -> pd.DataFrame:
    return frame.rolling(window, min_periods=1).apply(func, raw=True)


def _linear_slope(values: np.ndarray) -> float:
    if len(values) < 2 or not np.isfinite(values).all():
        return np.nan
    return float(np.polyfit(np.arange(len(values)), values, 1)[0])


def _linear_rsquare(values: np.ndarray) -> float:
    if len(values) < 2 or not np.isfinite(values).all() or np.std(values) <= 2e-5:
        return np.nan
    return float(np.corrcoef(np.arange(len(values)), values)[0, 1] ** 2)


def _linear_residual(values: np.ndarray) -> float:
    if len(values) < 2 or not np.isfinite(values).all():
        return np.nan
    return float(values[-1] - np.polyval(np.polyfit(np.arange(len(values)), values, 1), len(values) - 1))


class AlphaFeatureLibrary(FactorLibrary):
    """Alpha158（158 个）与 Alpha360（360 个）标准特征。"""

    author = "SVQuant"

    def _vwap(self) -> pd.DataFrame:
        """优先使用原始 VWAP；缺失时按成交额/成交量推导。"""
        if "vwap" in self.fields:
            return self["vwap"]
        return self.amount / (self.volume + EPSILON)


def _add_factor(name: str, description: str, calculator: Callable[[AlphaFeatureLibrary], pd.DataFrame]) -> None:
    def factor(self: AlphaFeatureLibrary) -> pd.DataFrame:
        return calculator(self)

    factor.__name__ = name
    factor.__doc__ = description
    setattr(AlphaFeatureLibrary, name, factor)


def _add_alpha360_factors() -> None:
    fields = {
        "close": lambda lib: lib.close,
        "open": lambda lib: lib.open,
        "high": lambda lib: lib.high,
        "low": lambda lib: lib.low,
        "vwap": lambda lib: lib._vwap(),
        "volume": lambda lib: lib.volume,
    }
    for field_name, getter in fields.items():
        for day in range(60):
            name = f"alpha360_{field_name}{day}"
            if field_name == "volume":
                _add_factor(
                    name,
                    f"Alpha360 VOLUME{day}。",
                    lambda lib, getter=getter, day=day: getter(lib).shift(day) / (lib.volume + EPSILON),
                )
            else:
                _add_factor(
                    name,
                    f"Alpha360 {field_name.upper()}{day}。",
                    lambda lib, getter=getter, day=day: getter(lib).shift(day) / lib.close,
                )


def _add_alpha158_factors() -> None:
    kbar = {
        "kmid": lambda lib: (lib.close - lib.open) / lib.open,
        "klen": lambda lib: (lib.high - lib.low) / lib.open,
        "kmid2": lambda lib: (lib.close - lib.open) / (lib.high - lib.low + EPSILON),
        "kup": lambda lib: (lib.high - np.maximum(lib.open, lib.close)) / lib.open,
        "kup2": lambda lib: (lib.high - np.maximum(lib.open, lib.close)) / (lib.high - lib.low + EPSILON),
        "klow": lambda lib: (np.minimum(lib.open, lib.close) - lib.low) / lib.open,
        "klow2": lambda lib: (np.minimum(lib.open, lib.close) - lib.low) / (lib.high - lib.low + EPSILON),
        "ksft": lambda lib: (2 * lib.close - lib.high - lib.low) / lib.open,
        "ksft2": lambda lib: (2 * lib.close - lib.high - lib.low) / (lib.high - lib.low + EPSILON),
    }
    for suffix, calculator in kbar.items():
        _add_factor(f"alpha158_{suffix}", f"Alpha158 {suffix.upper()}。", calculator)

    for field_name, getter in {
        "open": lambda lib: lib.open,
        "high": lambda lib: lib.high,
        "low": lambda lib: lib.low,
        "vwap": lambda lib: lib._vwap(),
    }.items():
        _add_factor(
            f"alpha158_{field_name}0",
            f"Alpha158 {field_name.upper()}0。",
            lambda lib, getter=getter: getter(lib) / lib.close,
        )

    for window in ROLLING_WINDOWS:
        rolling = lambda frame, window=window: frame.rolling(window, min_periods=1)
        close_change = lambda lib: lib.close - lib.close.shift(1)
        volume_change = lambda lib: lib.volume - lib.volume.shift(1)
        price_return = lambda lib: lib.close / lib.close.shift(1)
        volume_return = lambda lib: np.log(lib.volume / lib.volume.shift(1) + 1)
        factors = {
            "roc": lambda lib, window=window: lib.close.shift(window) / lib.close,
            "ma": lambda lib, rolling=rolling: rolling(lib.close).mean() / lib.close,
            "std": lambda lib, rolling=rolling: rolling(lib.close).std() / lib.close,
            "beta": lambda lib, window=window: _rolling_apply(lib.close, window, _linear_slope) / lib.close,
            "rsqr": lambda lib, window=window: _rolling_apply(lib.close, window, _linear_rsquare),
            "resi": lambda lib, window=window: _rolling_apply(lib.close, window, _linear_residual) / lib.close,
            "max": lambda lib, rolling=rolling: rolling(lib.high).max() / lib.close,
            "min": lambda lib, rolling=rolling: rolling(lib.low).min() / lib.close,
            "qtlu": lambda lib, rolling=rolling: rolling(lib.close).quantile(0.8) / lib.close,
            "qtld": lambda lib, rolling=rolling: rolling(lib.close).quantile(0.2) / lib.close,
            "rank": lambda lib, rolling=rolling: rolling(lib.close).rank(pct=True),
            "rsv": lambda lib, rolling=rolling: (lib.close - rolling(lib.low).min()) / (rolling(lib.high).max() - rolling(lib.low).min() + EPSILON),
            "imax": lambda lib, window=window: _rolling_apply(lib.high, window, lambda x: np.argmax(x) + 1) / window,
            "imin": lambda lib, window=window: _rolling_apply(lib.low, window, lambda x: np.argmin(x) + 1) / window,
            "imxd": lambda lib, window=window: (_rolling_apply(lib.high, window, lambda x: np.argmax(x) + 1) - _rolling_apply(lib.low, window, lambda x: np.argmin(x) + 1)) / window,
            "corr": lambda lib, rolling=rolling: rolling(lib.close).corr(np.log(lib.volume + 1)),
            "cord": lambda lib, rolling=rolling: rolling(price_return(lib)).corr(volume_return(lib)),
            "cntp": lambda lib, rolling=rolling: rolling((close_change(lib) > 0).astype(float)).mean(),
            "cntn": lambda lib, rolling=rolling: rolling((close_change(lib) < 0).astype(float)).mean(),
            "cntd": lambda lib, rolling=rolling: rolling((close_change(lib) > 0).astype(float)).mean() - rolling((close_change(lib) < 0).astype(float)).mean(),
            "sump": lambda lib, rolling=rolling: rolling(close_change(lib).clip(lower=0)).sum() / (rolling(close_change(lib).abs()).sum() + EPSILON),
            "sumn": lambda lib, rolling=rolling: rolling((-close_change(lib)).clip(lower=0)).sum() / (rolling(close_change(lib).abs()).sum() + EPSILON),
            "sumd": lambda lib, rolling=rolling: (rolling(close_change(lib).clip(lower=0)).sum() - rolling((-close_change(lib)).clip(lower=0)).sum()) / (rolling(close_change(lib).abs()).sum() + EPSILON),
            "vma": lambda lib, rolling=rolling: rolling(lib.volume).mean() / (lib.volume + EPSILON),
            "vstd": lambda lib, rolling=rolling: rolling(lib.volume).std() / (lib.volume + EPSILON),
            "wvma": lambda lib, rolling=rolling: rolling((price_return(lib) - 1).abs() * lib.volume).std() / (rolling((price_return(lib) - 1).abs() * lib.volume).mean() + EPSILON),
            "vsump": lambda lib, rolling=rolling: rolling(volume_change(lib).clip(lower=0)).sum() / (rolling(volume_change(lib).abs()).sum() + EPSILON),
            "vsumn": lambda lib, rolling=rolling: rolling((-volume_change(lib)).clip(lower=0)).sum() / (rolling(volume_change(lib).abs()).sum() + EPSILON),
            "vsumd": lambda lib, rolling=rolling: (rolling(volume_change(lib).clip(lower=0)).sum() - rolling((-volume_change(lib)).clip(lower=0)).sum()) / (rolling(volume_change(lib).abs()).sum() + EPSILON),
        }
        for suffix, calculator in factors.items():
            _add_factor(
                f"alpha158_{suffix}{window}",
                f"Alpha158 {suffix.upper()}{window}。",
                calculator,
            )


_add_alpha360_factors()
_add_alpha158_factors()
