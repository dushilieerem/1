"""V5 P0 research statistics: K-corrected threshold and Newey-West t.

Pure functions only. The trial ledger owns K; this module owns the math so the
same rule is used by the API, the report and the tests.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Iterable, Sequence


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def threshold(k: int, alpha: float = 0.05) -> float:
    """Bonferroni two-sided threshold t*(K) = Phi^-1(1 - alpha/(2K))."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("K 必须是大于等于 1 的整数")
    if not 0 < alpha < 1:
        raise ValueError("alpha 必须在 0 与 1 之间")
    return NormalDist().inv_cdf(1 - alpha / (2 * k))


def _values(series: Iterable) -> list[float]:
    """Accept numbers or {value: ...} / {ic: ...} dicts; ignore non-finite."""
    out: list[float] = []
    for item in series:
        value = item.get("value", item.get("ic")) if isinstance(item, dict) else item
        if _finite(value):
            out.append(float(value))
    return out


def default_lags(n: int) -> int:
    """Newey-West (1994) rule: floor(4 * (n/100)^(2/9))."""
    if n < 2:
        return 0
    return min(n - 1, int(math.floor(4 * (n / 100.0) ** (2.0 / 9.0))))


def newey_west_t(series: Sequence | Iterable, lags: int | None = None) -> dict:
    """HAC t statistic for the mean of a daily series.

    Bartlett kernel, no small-sample correction. ``series`` is the daily Rank
    IC sequence (dicts with ``value`` or plain numbers). Missing/non-finite
    observations are dropped before counting.
    """
    values = _values(series)
    n = len(values)
    if n < 2:
        raise ValueError("有效序列少于 2 个观测，无法计算 t 值")
    if lags is None:
        lags = default_lags(n)
    if isinstance(lags, bool) or not isinstance(lags, int) or lags < 0 or lags >= n:
        raise ValueError("滞后阶数必须在 0 与 n-1 之间")
    mean = sum(values) / n
    errors = [v - mean for v in values]
    gamma0 = sum(e * e for e in errors) / n
    long_run = gamma0
    for lag in range(1, lags + 1):
        gamma = sum(errors[t] * errors[t - lag] for t in range(lag, n)) / n
        weight = 1.0 - lag / (lags + 1.0)
        long_run += 2.0 * weight * gamma
    if long_run <= 1e-18:
        raise ValueError("序列方差为 0，无法计算 Newey-West t 值")
    standard_error = math.sqrt(long_run / n)
    return {"mean": mean, "t": mean / standard_error, "n": n, "lags": lags}


def significance(series: Sequence | Iterable, k: int, direction: str = "positive",
                 min_ic: float = 0.02, lags: int | None = None) -> dict:
    """Evaluate the pre-registered Rank IC direction and K-corrected t.

    ``direction`` is positive|negative; ``min_ic`` is the absolute IC floor.
    The caller decides whether the candidate's other checks pass.
    """
    if direction not in ("positive", "negative"):
        raise ValueError("方向必须是 positive 或 negative")
    if not _finite(min_ic) or not 0 <= float(min_ic) <= 1:
        raise ValueError("最低 IC 必须在 0 与 1 之间")
    result = newey_west_t(series, lags)
    sign = 1 if direction == "positive" else -1
    signed_mean = result["mean"] * sign
    signed_t = result["t"] * sign
    required = threshold(k)
    return {
        **result,
        "signed_mean": signed_mean,
        "signed_t": signed_t,
        "threshold": required,
        "min_ic": float(min_ic),
        "passed": signed_mean >= float(min_ic) and signed_t >= required,
    }
