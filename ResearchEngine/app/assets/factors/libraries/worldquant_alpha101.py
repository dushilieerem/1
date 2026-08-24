"""WorldQuant Alpha 101 因子库。

本模块按 Kakushadze 的《101 Formulaic Alphas》实现公开的 101 条公式，
以 SVQuant 的 ``FactorLibrary`` 面板契约提供 ``alpha001`` 到 ``alpha101``。

实现约定：

* 所有输入和输出都是 ``日期 × 标的`` 的 ``pandas.DataFrame``；
* ``adv{n}`` 优先使用 ``amount``，否则使用 ``close * volume`` 计算平均日成交额；
* ``vwap`` 优先使用面板字段，否则使用 ``amount / volume``，再否则使用典型价格；
* ``indneutralize`` 优先使用 ``sector``、``industry``、``subindustry`` 字段；
  没有分类字段时退化为截面去均值，并不声称与原始分类中性化口径逐值一致；
* 论文规定的非整数窗口按 floor 转为整数窗口；
* 公式只使用当日及历史数据，不使用未来数据。

公式来源：Kakushadze, ``101 Formulaic Alphas``, arXiv:1601.00991。
论文同时说明公式版权归 WorldQuant LLC 所有；本文件仅实现公开论文中的公式，
不包含 WorldQuant 专有数据、运行时或因子数值。
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from app.quantcore import FactorLibrary


EPSILON = 1e-12


def _window(value: int | float) -> int:
    """按论文规则把窗口转换为至少为 1 的整数。"""
    return max(1, int(np.floor(float(value))))


def _rank(frame: pd.DataFrame) -> pd.DataFrame:
    """截面百分位秩。"""
    return frame.rank(axis=1, method="average", pct=True)


def _rolling_apply(
    frame: pd.DataFrame, window: int | float, func: Callable[[np.ndarray], float]
) -> pd.DataFrame:
    size = _window(window)
    return frame.rolling(size, min_periods=size).apply(func, raw=True)


def _ts_rank(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    """时间序列中当前值的百分位秩。"""
    size = _window(window)
    try:
        return frame.rolling(size, min_periods=size).rank(pct=True)
    except AttributeError:  # pragma: no cover - 兼容较旧 pandas
        return _rolling_apply(
            frame,
            size,
            lambda values: float(pd.Series(values).rank(pct=True).iloc[-1]),
        )


def _ts_sum(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    size = _window(window)
    return frame.rolling(size, min_periods=size).sum()


def _ts_mean(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    size = _window(window)
    return frame.rolling(size, min_periods=size).mean()


def _ts_std(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    size = _window(window)
    return frame.rolling(size, min_periods=size).std()


def _ts_min(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    size = _window(window)
    return frame.rolling(size, min_periods=size).min()


def _ts_max(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    size = _window(window)
    return frame.rolling(size, min_periods=size).max()


def _ts_argmin(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    return _rolling_apply(frame, window, lambda values: float(np.argmin(values) + 1))


def _ts_argmax(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    return _rolling_apply(frame, window, lambda values: float(np.argmax(values) + 1))


def _ts_product(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    return _rolling_apply(frame, window, lambda values: float(np.prod(values)))


def _delay(frame: pd.DataFrame, days: int | float) -> pd.DataFrame:
    return frame.shift(_window(days))


def _delta(frame: pd.DataFrame, days: int | float) -> pd.DataFrame:
    return frame.diff(_window(days))


def _correlation(
    left: pd.DataFrame, right: pd.DataFrame, window: int | float
) -> pd.DataFrame:
    size = _window(window)
    return left.rolling(size, min_periods=size).corr(right).replace(
        [np.inf, -np.inf], np.nan
    )


def _covariance(
    left: pd.DataFrame, right: pd.DataFrame, window: int | float
) -> pd.DataFrame:
    size = _window(window)
    return left.rolling(size, min_periods=size).cov(right).replace(
        [np.inf, -np.inf], np.nan
    )


def _decay_linear(frame: pd.DataFrame, window: int | float) -> pd.DataFrame:
    size = _window(window)
    weights = np.arange(size, 0, -1, dtype=float)
    weights /= weights.sum()
    return _rolling_apply(frame, size, lambda values: float(np.dot(values, weights)))


def _scale(frame: pd.DataFrame, target: float = 1.0) -> pd.DataFrame:
    denominator = frame.abs().sum(axis=1).replace(0.0, np.nan)
    return frame.mul(target).div(denominator, axis=0)


def _signed_power(
    frame: pd.DataFrame, exponent: float | pd.DataFrame
) -> pd.DataFrame:
    """实数域 signedpower，避免负底数的非整数幂产生复数。"""
    return np.sign(frame) * np.power(frame.abs(), exponent)


def _conditional(
    condition: pd.DataFrame,
    when_true: pd.DataFrame | float | int,
    when_false: pd.DataFrame | float | int,
) -> pd.DataFrame:
    if not isinstance(when_true, pd.DataFrame):
        when_true = pd.DataFrame(
            when_true, index=condition.index, columns=condition.columns
        )
    if not isinstance(when_false, pd.DataFrame):
        when_false = pd.DataFrame(
            when_false, index=condition.index, columns=condition.columns
        )
    return when_true.where(condition, when_false)


def _bool_signal(condition: pd.DataFrame, multiplier: float = 1.0) -> pd.DataFrame:
    return condition.astype(float) * multiplier


def _safe_divide(
    numerator: pd.DataFrame | float | int,
    denominator: pd.DataFrame,
    epsilon: float = EPSILON,
) -> pd.DataFrame:
    if not isinstance(numerator, pd.DataFrame):
        numerator = pd.DataFrame(
            numerator, index=denominator.index, columns=denominator.columns
        )
    return numerator.div(denominator.where(denominator.abs() > epsilon))


def _field(library: "WorldQuantAlpha101Library", name: str) -> pd.DataFrame | None:
    if name in library.fields:
        return library[name]
    return None


def _dollar_volume(library: "WorldQuantAlpha101Library") -> pd.DataFrame:
    amount = _field(library, "amount")
    if amount is not None:
        return amount
    return library.close * library.volume


def _vwap(library: "WorldQuantAlpha101Library") -> pd.DataFrame:
    vwap = _field(library, "vwap")
    if vwap is not None:
        return vwap
    amount = _field(library, "amount")
    if amount is not None:
        return _safe_divide(amount, library.volume)
    return (library.high + library.low + library.close) / 3.0


def _returns(library: "WorldQuantAlpha101Library") -> pd.DataFrame:
    return library.close.pct_change()


def _adv(
    library: "WorldQuantAlpha101Library", window: int | float
) -> pd.DataFrame:
    return _ts_mean(_dollar_volume(library), window)


def _cap(library: "WorldQuantAlpha101Library") -> pd.DataFrame:
    cap = _field(library, "cap")
    if cap is not None:
        return cap
    total_mv = _field(library, "total_mv")
    if total_mv is not None:
        return total_mv
    # 只为没有市值字段的研究样本提供可运行近似；生产研究应提供 total_mv/cap。
    return library.close * library.volume


def _group_field(
    library: "WorldQuantAlpha101Library", level: str
) -> pd.DataFrame | None:
    for name in (level, f"{level}_code"):
        value = _field(library, name)
        if value is not None:
            return value
    return None


def _indneutralize(
    library: "WorldQuantAlpha101Library", frame: pd.DataFrame, level: str
) -> pd.DataFrame:
    groups = _group_field(library, level)
    if groups is None:
        return frame.sub(frame.mean(axis=1), axis=0)

    groups = groups.reindex(index=frame.index, columns=frame.columns)
    result = frame.copy()
    labels = pd.unique(groups.to_numpy().ravel())
    for label in labels:
        if pd.isna(label):
            continue
        mask = groups.eq(label)
        mean = frame.where(mask).mean(axis=1)
        result = result.where(~mask, frame.sub(mean, axis=0))

    missing = groups.isna()
    if missing.any().any():
        mean = frame.where(missing).mean(axis=1)
        result = result.where(~missing, frame.sub(mean, axis=0))
    return result


class WorldQuantAlpha101Library(FactorLibrary):
    """WorldQuant 101 Formulaic Alphas 的 SVQuant 原生实现。"""

    author = "SVQuant"


def _alpha001(library):
    returns = _returns(library)
    selected = _ts_std(returns, 20).where(returns < 0, library.close)
    return _rank(_ts_argmax(_signed_power(selected, 2.0), 5)) - 0.5


def _alpha002(library):
    return -_correlation(
        _rank(_delta(np.log(library.volume), 2)),
        _rank(_safe_divide(library.close - library.open, library.open)),
        6,
    )


def _alpha003(library):
    return -_correlation(_rank(library.open), _rank(library.volume), 10)


def _alpha004(library):
    return -_ts_rank(_rank(library.low), 9)


def _alpha005(library):
    vwap = _vwap(library)
    return _rank(library.open - _ts_sum(vwap, 10) / 10.0) * -_rank(
        library.close - vwap
    ).abs()


def _alpha006(library):
    return -_correlation(library.open, library.volume, 10)


def _alpha007(library):
    delta = _delta(library.close, 7)
    value = -_ts_rank(delta.abs(), 60) * np.sign(delta)
    return _conditional(_adv(library, 20) < library.volume, value, -1.0)


def _alpha008(library):
    value = _ts_sum(library.open, 5) * _ts_sum(_returns(library), 5)
    return -_rank(value - _delay(value, 10))


def _alpha009(library):
    delta = _delta(library.close, 1)
    return _conditional(
        _ts_min(delta, 5) > 0,
        delta,
        _conditional(_ts_max(delta, 5) < 0, delta, -delta),
    )


def _alpha010(library):
    delta = _delta(library.close, 1)
    value = _conditional(
        _ts_min(delta, 4) > 0,
        delta,
        _conditional(_ts_max(delta, 4) < 0, delta, -delta),
    )
    return _rank(value)


def _alpha011(library):
    vwap_close = _vwap(library) - library.close
    return (
        _rank(_ts_max(vwap_close, 3)) + _rank(_ts_min(vwap_close, 3))
    ) * _rank(_delta(library.volume, 3))


def _alpha012(library):
    return np.sign(_delta(library.volume, 1)) * -_delta(library.close, 1)


def _alpha013(library):
    return -_rank(_covariance(_rank(library.close), _rank(library.volume), 5))


def _alpha014(library):
    return -_rank(_delta(_returns(library), 3)) * _correlation(
        library.open, library.volume, 10
    )


def _alpha015(library):
    value = _rank(
        _correlation(_rank(library.high), _rank(library.volume), 3)
    )
    return -_ts_sum(value, 3)


def _alpha016(library):
    return -_rank(_covariance(_rank(library.high), _rank(library.volume), 5))


def _alpha017(library):
    return (
        -_rank(_ts_rank(library.close, 10))
        * _rank(_delta(_delta(library.close, 1), 1))
        * _rank(_ts_rank(_safe_divide(library.volume, _adv(library, 20)), 5))
    )


def _alpha018(library):
    value = (
        _ts_std((library.close - library.open).abs(), 5)
        + library.close
        - library.open
        + _correlation(library.close, library.open, 10)
    )
    return -_rank(value)


def _alpha019(library):
    delta = _delta(library.close, 7)
    return -np.sign((library.close - _delay(library.close, 7)) + delta) * (
        1.0 + _rank(1.0 + _ts_sum(_returns(library), 250))
    )


def _alpha020(library):
    return (
        -_rank(library.open - _delay(library.high, 1))
        * _rank(library.open - _delay(library.close, 1))
        * _rank(library.open - _delay(library.low, 1))
    )


def _alpha021(library):
    mean8 = _ts_sum(library.close, 8) / 8.0
    mean2 = _ts_sum(library.close, 2) / 2.0
    ratio = _safe_divide(library.volume, _adv(library, 20))
    value = _conditional(ratio > 1.0, 1.0, -1.0)
    value = _conditional(mean2 < mean8 - _ts_std(library.close, 8), 1.0, value)
    return _conditional(mean8 + _ts_std(library.close, 8) < mean2, -1.0, value)


def _alpha022(library):
    return -_delta(_correlation(library.high, library.volume, 5), 5) * _rank(
        _ts_std(library.close, 20)
    )


def _alpha023(library):
    return _conditional(
        _ts_sum(library.high, 20) / 20.0 < library.high,
        -_delta(library.high, 2),
        0.0,
    )


def _alpha024(library):
    mean100 = _ts_sum(library.close, 100) / 100.0
    change = _safe_divide(_delta(mean100, 100), _delay(library.close, 100))
    return _conditional(
        change <= 0.05,
        -(library.close - _ts_min(library.close, 100)),
        -_delta(library.close, 3),
    )


def _alpha025(library):
    return _rank(
        -_returns(library)
        * _adv(library, 20)
        * _vwap(library)
        * (library.high - library.close)
    )


def _alpha026(library):
    value = _correlation(
        _ts_rank(library.volume, 5), _ts_rank(library.high, 5), 5
    )
    return -_ts_max(value, 3)


def _alpha027(library):
    value = _rank(
        _ts_sum(
            _correlation(_rank(library.volume), _rank(_vwap(library)), 6), 2
        )
        / 2.0
    )
    return _conditional(value > 0.5, -1.0, 1.0)


def _alpha028(library):
    return _scale(
        _correlation(_adv(library, 20), library.low, 5)
        + (library.high + library.low) / 2.0
        - library.close
    )


def _alpha029(library):
    delta = _rank(_delta(library.close - 1.0, 5))
    inner = _rank(_rank(-delta))
    inner = _ts_min(inner, 2)
    inner = _ts_sum(inner, 1)
    inner = _scale(np.log(inner))
    inner = _rank(_rank(inner))
    return _ts_min(_ts_product(inner, 1), 5) + _ts_rank(
        _delay(-_returns(library), 6), 5
    )


def _alpha030(library):
    sign_sum = (
        np.sign(_delta(library.close, 1))
        + np.sign(_delay(library.close, 1) - _delay(library.close, 2))
        + np.sign(_delay(library.close, 2) - _delay(library.close, 3))
    )
    return (1.0 - _rank(sign_sum)) * _ts_sum(library.volume, 5) / _ts_sum(
        library.volume, 20
    )


def _alpha031(library):
    first = _rank(
        _rank(
            _rank(
                _decay_linear(-_rank(_rank(_delta(library.close, 10))), 10)
            )
        )
    )
    second = _rank(-_delta(library.close, 3))
    third = np.sign(_scale(_correlation(_adv(library, 20), library.low, 12)))
    return first + second + third


def _alpha032(library):
    return _scale(_ts_sum(library.close, 7) / 7.0 - library.close) + 20.0 * _scale(
        _correlation(_vwap(library), _delay(library.close, 5), 230)
    )


def _alpha033(library):
    return _rank(-((1.0 - _safe_divide(library.open, library.close)) ** 1))


def _alpha034(library):
    return _rank(
        (1.0 - _rank(_safe_divide(_ts_std(_returns(library), 2), _ts_std(_returns(library), 5))))
        + (1.0 - _rank(_delta(library.close, 1)))
    )


def _alpha035(library):
    return (
        _ts_rank(library.volume, 32)
        * (1.0 - _ts_rank(library.close + library.high - library.low, 16))
        * (1.0 - _ts_rank(_returns(library), 32))
    )


def _alpha036(library):
    return (
        2.21
        * _rank(_correlation(library.close - library.open, _delay(library.volume, 1), 15))
        + 0.7 * _rank(library.open - library.close)
        + 0.73 * _rank(_ts_rank(_delay(-_returns(library), 6), 5))
        + _rank(_correlation(_vwap(library), _adv(library, 20), 6).abs())
        + 0.6
        * _rank(
            (_ts_sum(library.close, 200) / 200.0 - library.open)
            * (library.close - library.open)
        )
    )


def _alpha037(library):
    return _rank(
        _correlation(_delay(library.open - library.close, 1), library.close, 200)
    ) + _rank(library.open - library.close)


def _alpha038(library):
    return -_rank(_ts_rank(library.close, 10)) * _rank(
        _safe_divide(library.close, library.open)
    )


def _alpha039(library):
    return -_rank(
        _delta(library.close, 7)
        * (1.0 - _rank(_decay_linear(_safe_divide(library.volume, _adv(library, 20)), 9)))
    ) * (1.0 + _rank(_ts_sum(_returns(library), 250)))


def _alpha040(library):
    return -_rank(_ts_std(library.high, 10)) * _correlation(
        library.high, library.volume, 10
    )


def _alpha041(library):
    return np.sqrt(library.high * library.low) - _vwap(library)


def _alpha042(library):
    vwap = _vwap(library)
    return _safe_divide(_rank(vwap - library.close), _rank(vwap + library.close))


def _alpha043(library):
    return _ts_rank(_safe_divide(library.volume, _adv(library, 20)), 20) * _ts_rank(
        -_delta(library.close, 7), 8
    )


def _alpha044(library):
    return -_correlation(library.high, _rank(library.volume), 5)


def _alpha045(library):
    return -(
        _rank(_ts_sum(_delay(library.close, 5), 20) / 20.0)
        * _correlation(library.close, library.volume, 2)
        * _rank(
            _correlation(_ts_sum(library.close, 5), _ts_sum(library.close, 20), 2)
        )
    )


def _alpha046(library):
    value = (
        (_delay(library.close, 20) - _delay(library.close, 10)) / 10.0
        - (_delay(library.close, 10) - library.close) / 10.0
    )
    return _conditional(
        value > 0.25,
        -1.0,
        _conditional(value < 0.0, 1.0, -(library.close - _delay(library.close, 1))),
    )


def _alpha047(library):
    return (
        _safe_divide(_rank(_safe_divide(1.0, library.close)) * library.volume, _adv(library, 20))
        * _safe_divide(
            library.high * _rank(library.high - library.close),
            _ts_sum(library.high, 5) / 5.0,
        )
        - _rank(_vwap(library) - _delay(_vwap(library), 5))
    )


def _alpha048(library):
    delta = _delta(library.close, 1)
    delayed_delta = _delta(_delay(library.close, 1), 1)
    numerator = _correlation(delta, delayed_delta, 250) * delta / library.close
    denominator = _ts_sum(_safe_divide(delta, _delay(library.close, 1)) ** 2, 250)
    return _safe_divide(_indneutralize(library, numerator, "subindustry"), denominator)


def _alpha049(library):
    value = (
        (_delay(library.close, 20) - _delay(library.close, 10)) / 10.0
        - (_delay(library.close, 10) - library.close) / 10.0
    )
    return _conditional(value < -0.1, 1.0, -(library.close - _delay(library.close, 1)))


def _alpha050(library):
    return -_ts_max(
        _rank(_correlation(_rank(library.volume), _rank(_vwap(library)), 5)), 5
    )


def _alpha051(library):
    value = (
        (_delay(library.close, 20) - _delay(library.close, 10)) / 10.0
        - (_delay(library.close, 10) - library.close) / 10.0
    )
    return _conditional(value < -0.05, 1.0, -(library.close - _delay(library.close, 1)))


def _alpha052(library):
    low_min = _ts_min(library.low, 5)
    return (
        (-low_min + _delay(low_min, 5))
        * _rank(
            (_ts_sum(_returns(library), 240) - _ts_sum(_returns(library), 20)) / 220.0
        )
        * _ts_rank(library.volume, 5)
    )


def _alpha053(library):
    value = _safe_divide(
        (library.close - library.low) - (library.high - library.close),
        library.close - library.low,
    )
    return -_delta(value, 9)


def _alpha054(library):
    numerator = (library.low - library.close) * np.power(library.open, 5)
    denominator = (library.low - library.high) * np.power(library.close, 5)
    return -_safe_divide(numerator, denominator)


def _alpha055(library):
    low_min = _ts_min(library.low, 12)
    high_max = _ts_max(library.high, 12)
    inner = _safe_divide(library.close - low_min, high_max - low_min)
    return -_correlation(_rank(inner), _rank(library.volume), 6)


def _alpha056(library):
    first = _rank(
        _safe_divide(
            _ts_sum(_returns(library), 10),
            _ts_sum(_ts_sum(_returns(library), 2), 3),
        )
    )
    return -first * _rank(_returns(library) * _cap(library))


def _alpha057(library):
    vwap = _vwap(library)
    return -_safe_divide(
        library.close - vwap,
        _decay_linear(_rank(_ts_argmax(library.close, 30)), 2),
    )


def _alpha058(library):
    value = _correlation(
        _indneutralize(library, _vwap(library), "sector"), library.volume, 3.92795
    )
    return -_ts_rank(_decay_linear(value, 7.89291), 5.50322)


def _alpha059(library):
    vwap = _vwap(library)
    neutralized = _indneutralize(library, vwap * 0.728317 + vwap * (1 - 0.728317), "industry")
    value = _correlation(neutralized, library.volume, 4.25197)
    return -_ts_rank(_decay_linear(value, 16.2289), 8.19648)


def _alpha060(library):
    denominator = (library.high - library.low).where(
        (library.high - library.low).abs() > EPSILON, np.nan
    )
    inner = (
        ((library.close - library.low) - (library.high - library.close))
        / denominator
        * library.volume
    )
    return -(2.0 * _scale(_rank(inner)) - _scale(_rank(_ts_argmax(library.close, 10))))


def _alpha061(library):
    vwap = _vwap(library)
    return _bool_signal(
        _rank(vwap - _ts_min(vwap, 16.1219))
        < _rank(_correlation(vwap, _adv(library, 180), 17.9282))
    )


def _alpha062(library):
    left = _rank(
        _correlation(vwap := _vwap(library), _ts_sum(_adv(library, 20), 22.4101), 9.91009)
    )
    right = _rank(
        (_rank(library.open) + _rank(library.open))
        < (_rank((library.high + library.low) / 2.0) + _rank(library.high))
    )
    return _bool_signal(left < right, -1.0)


def _alpha063(library):
    vwap = _vwap(library)
    left = _rank(
        _decay_linear(
            _delta(_indneutralize(library, library.close, "industry"), 2.25164),
            8.22237,
        )
    )
    right = _rank(
        _decay_linear(
            _correlation(
                vwap * 0.318108 + library.open * (1 - 0.318108),
                _ts_sum(_adv(library, 180), 37.2467),
                13.557,
            ),
            12.2883,
        )
    )
    return -(left - right)


def _alpha064(library):
    first = library.open * 0.178404 + library.low * (1 - 0.178404)
    second = (library.high + library.low) / 2.0 * 0.178404 + _vwap(library) * (1 - 0.178404)
    left = _rank(
        _correlation(
            _ts_sum(first, 12.7054),
            _ts_sum(_adv(library, 120), 12.7054),
            16.6208,
        )
    )
    right = _rank(_delta(second, 3.69741))
    return _bool_signal(left < right, -1.0)


def _alpha065(library):
    first = library.open * 0.00817205 + _vwap(library) * (1 - 0.00817205)
    left = _rank(
        _correlation(first, _ts_sum(_adv(library, 60), 8.6911), 6.40374)
    )
    right = _rank(library.open - _ts_min(library.open, 13.635))
    return _bool_signal(left < right, -1.0)


def _alpha066(library):
    vwap = _vwap(library)
    second = _safe_divide(
        library.low * 0.96633 + library.low * (1 - 0.96633) - vwap,
        library.open - (library.high + library.low) / 2.0,
    )
    value = _rank(_decay_linear(_delta(vwap, 3.51013), 7.23052)) + _ts_rank(
        _decay_linear(second, 11.4157), 6.72611
    )
    return -value


def _alpha067(library):
    left = _rank(library.high - _ts_min(library.high, 2.14593))
    right = _rank(
        _correlation(
            _indneutralize(library, _vwap(library), "sector"),
            _indneutralize(library, _adv(library, 20), "subindustry"),
            6.02936,
        )
    )
    return -_signed_power(left, right)


def _alpha068(library):
    left = _ts_rank(
        _correlation(_rank(library.high), _rank(_adv(library, 15)), 8.91644),
        13.9333,
    )
    right = _rank(
        _delta(library.close * 0.518371 + library.low * (1 - 0.518371), 1.06157)
    )
    return _bool_signal(left < right, -1.0)


def _alpha069(library):
    vwap = _vwap(library)
    left = _rank(
        _ts_max(
            _delta(_indneutralize(library, vwap, "industry"), 2.72412),
            4.79344,
        )
    )
    exponent = _ts_rank(
        _correlation(
            library.close * 0.490655 + vwap * (1 - 0.490655),
            _adv(library, 20),
            4.92416,
        ),
        9.0615,
    )
    return -_signed_power(left, exponent)


def _alpha070(library):
    exponent = _ts_rank(
        _correlation(
            _indneutralize(library, library.close, "industry"),
            _adv(library, 50),
            17.8256,
        ),
        17.9171,
    )
    return -_signed_power(_rank(_delta(_vwap(library), 1.29456)), exponent)


def _alpha071(library):
    first = _ts_rank(
        _decay_linear(
            _correlation(
                _ts_rank(library.close, 3.43976),
                _ts_rank(_adv(library, 180), 12.0647),
                18.0175,
            ),
            4.20501,
        ),
        15.6948,
    )
    second = _ts_rank(
        _decay_linear(
            _rank(library.low + library.open - 2.0 * _vwap(library)) ** 2,
            16.4662,
        ),
        4.4388,
    )
    return np.maximum(first, second)


def _alpha072(library):
    numerator = _rank(
        _decay_linear(
            _correlation((library.high + library.low) / 2.0, _adv(library, 40), 8.93345),
            10.1519,
        )
    )
    denominator = _rank(
        _decay_linear(
            _correlation(
                _ts_rank(_vwap(library), 3.72469),
                _ts_rank(library.volume, 18.5188),
                6.86671,
            ),
            2.95011,
        )
    )
    return _safe_divide(numerator, denominator)


def _alpha073(library):
    vwap = _vwap(library)
    first = _rank(_decay_linear(_delta(vwap, 4.72775), 2.91864))
    weighted = library.open * 0.147155 + library.low * (1 - 0.147155)
    second = _ts_rank(
        _decay_linear(-_safe_divide(_delta(weighted, 2.03608), weighted), 3.33829),
        16.7411,
    )
    return -np.maximum(first, second)


def _alpha074(library):
    vwap = _vwap(library)
    left = _rank(
        _correlation(library.close, _ts_sum(_adv(library, 30), 37.4843), 15.1365)
    )
    right = _rank(
        _correlation(
            _rank(library.high * 0.0261661 + vwap * (1 - 0.0261661)),
            _rank(library.volume),
            11.4793,
        )
    )
    return _bool_signal(left < right, -1.0)


def _alpha075(library):
    left = _rank(_correlation(_vwap(library), library.volume, 4.24304))
    right = _rank(
        _correlation(_rank(library.low), _rank(_adv(library, 50)), 12.4413)
    )
    return _bool_signal(left < right)


def _alpha076(library):
    first = _rank(_decay_linear(_delta(_vwap(library), 1.24383), 11.8259))
    second = _ts_rank(
        _decay_linear(
            _ts_rank(
                _correlation(
                    _indneutralize(library, library.low, "sector"),
                    _adv(library, 81),
                    8.14941,
                ),
                19.569,
            ),
            17.1543,
        ),
        19.383,
    )
    return -np.maximum(first, second)


def _alpha077(library):
    first = _rank(
        _decay_linear(
            (library.high + library.low) / 2.0 + library.high - (_vwap(library) + library.high),
            20.0451,
        )
    )
    second = _rank(
        _decay_linear(
            _correlation((library.high + library.low) / 2.0, _adv(library, 40), 3.1614),
            5.64125,
        )
    )
    return np.minimum(first, second)


def _alpha078(library):
    vwap = _vwap(library)
    left = library.low * 0.352233 + vwap * (1 - 0.352233)
    numerator = _rank(
        _correlation(
            _ts_sum(left, 19.7428),
            _ts_sum(_adv(library, 40), 19.7428),
            6.83313,
        )
    )
    exponent = _rank(
        _correlation(_rank(vwap), _rank(library.volume), 5.77492)
    )
    return _signed_power(numerator, exponent)


def _alpha079(library):
    first = _indneutralize(
        library,
        library.close * 0.60733 + library.open * (1 - 0.60733),
        "sector",
    )
    left = _rank(_delta(first, 1.23438))
    right = _rank(
        _correlation(
            _ts_rank(_vwap(library), 3.60973),
            _ts_rank(_adv(library, 150), 9.18637),
            14.6644,
        )
    )
    return _bool_signal(left < right)


def _alpha080(library):
    first = _indneutralize(
        library,
        library.open * 0.868128 + library.high * (1 - 0.868128),
        "industry",
    )
    base = _rank(np.sign(_delta(first, 4.04545)))
    exponent = _ts_rank(_correlation(library.high, _adv(library, 10), 5.11456), 5.53756)
    return -_signed_power(base, exponent)


def _alpha081(library):
    vwap = _vwap(library)
    base = _rank(
        _correlation(vwap, _ts_sum(_adv(library, 10), 49.6054), 8.47743)
    ) ** 4
    left = _rank(np.log(_ts_product(base, 14.9655)))
    right = _rank(_correlation(_rank(vwap), _rank(library.volume), 5.07914))
    return _bool_signal(left < right, -1.0)


def _alpha082(library):
    first = _rank(_decay_linear(_delta(library.open, 1.46063), 14.8717))
    second = _ts_rank(
        _decay_linear(
            _correlation(
                _indneutralize(library, library.volume, "sector"),
                library.open * 0.634196 + library.open * (1 - 0.634196),
                17.4842,
            ),
            6.92131,
        ),
        13.4283,
    )
    return -np.minimum(first, second)


def _alpha083(library):
    mean5 = _ts_sum(library.close, 5) / 5.0
    numerator = _rank(_rank(library.volume)) * _rank(
        _delay(_safe_divide(library.high - library.low, mean5), 2)
    )
    denominator = _safe_divide(
        _safe_divide(library.high - library.low, mean5), _vwap(library) - library.close
    )
    return _safe_divide(numerator, denominator)


def _alpha084(library):
    base = _ts_rank(
        _vwap(library) - _ts_max(_vwap(library), 15.3217), 20.7127
    )
    return _signed_power(base, _delta(library.close, 4.96796))


def _alpha085(library):
    vwap = _vwap(library)
    numerator = _rank(
        _correlation(
            library.high * 0.876703 + library.close * (1 - 0.876703),
            _adv(library, 30),
            9.61331,
        )
    )
    exponent = _rank(
        _correlation(
            _ts_rank((library.high + library.low) / 2.0, 3.70596),
            _ts_rank(library.volume, 10.1595),
            7.11408,
        )
    )
    return _signed_power(numerator, exponent)


def _alpha086(library):
    left = _ts_rank(
        _correlation(library.close, _ts_sum(_adv(library, 20), 14.7444), 6.00049),
        20.4195,
    )
    right = _rank((library.open + library.close) - (_vwap(library) + library.open))
    return _bool_signal(left < right, -1.0)


def _alpha087(library):
    vwap = _vwap(library)
    first = _rank(
        _decay_linear(
            _delta(library.close * 0.369701 + vwap * (1 - 0.369701), 1.91233),
            2.65461,
        )
    )
    second = _ts_rank(
        _decay_linear(
            _correlation(
                _indneutralize(library, _adv(library, 81), "industry"),
                library.close,
                13.4132,
            ).abs(),
            4.89768,
        ),
        14.4535,
    )
    return -np.maximum(first, second)


def _alpha088(library):
    first = _rank(
        _decay_linear(
            _rank(library.open) + _rank(library.low) - _rank(library.high) - _rank(library.close),
            8.06882,
        )
    )
    second = _ts_rank(
        _decay_linear(
            _correlation(
                _ts_rank(library.close, 8.44728),
                _ts_rank(_adv(library, 60), 20.6966),
                8.01266,
            ),
            6.65053,
        ),
        2.61957,
    )
    return np.minimum(first, second)


def _alpha089(library):
    vwap = _vwap(library)
    first = _ts_rank(
        _decay_linear(
            _correlation(
                library.low * 0.967285 + library.low * (1 - 0.967285),
                _adv(library, 10),
                6.94279,
            ),
            5.51607,
        ),
        3.79744,
    )
    second = _ts_rank(
        _decay_linear(
            _delta(_indneutralize(library, vwap, "industry"), 3.48158),
            10.1466,
        ),
        15.3012,
    )
    return first - second


def _alpha090(library):
    exponent = _ts_rank(
        _correlation(
            _indneutralize(library, _adv(library, 40), "subindustry"),
            library.low,
            5.38375,
        ),
        3.21856,
    )
    return -_signed_power(_rank(library.close - _ts_max(library.close, 4.66719)), exponent)


def _alpha091(library):
    first = _ts_rank(
        _decay_linear(
            _decay_linear(
                _correlation(
                    _indneutralize(library, library.close, "industry"),
                    library.volume,
                    9.74928,
                ),
                16.398,
            ),
            3.83219,
        ),
        4.8667,
    )
    second = _rank(_decay_linear(_correlation(_vwap(library), _adv(library, 30), 4.01303), 2.6809))
    return -(first - second)


def _alpha092(library):
    first_condition = (
        (library.high + library.low) / 2.0 + library.close
    ) < (library.low + library.open)
    first = _ts_rank(_decay_linear(first_condition.astype(float), 14.7221), 18.8683)
    second = _ts_rank(
        _decay_linear(
            _correlation(_rank(library.low), _rank(_adv(library, 30)), 7.58555),
            6.94024,
        ),
        6.80584,
    )
    return np.minimum(first, second)


def _alpha093(library):
    first = _ts_rank(
        _decay_linear(
            _correlation(
                _indneutralize(library, _vwap(library), "industry"),
                _adv(library, 81),
                17.4193,
            ),
            19.848,
        ),
        7.54455,
    )
    second = _rank(
        _decay_linear(
            _delta(
                library.close * 0.524434 + _vwap(library) * (1 - 0.524434),
                2.77377,
            ),
            16.2664,
        )
    )
    return _safe_divide(first, second)


def _alpha094(library):
    vwap = _vwap(library)
    exponent = _ts_rank(
        _correlation(
            _ts_rank(vwap, 19.6462),
            _ts_rank(_adv(library, 60), 4.02992),
            18.0926,
        ),
        2.70756,
    )
    return -_signed_power(_rank(vwap - _ts_min(vwap, 11.5783)), exponent)


def _alpha095(library):
    left = _rank(library.open - _ts_min(library.open, 12.4105))
    right = _ts_rank(
        _rank(
            _correlation(
                _ts_sum((library.high + library.low) / 2.0, 19.1351),
                _ts_sum(_adv(library, 40), 19.1351),
                12.8742,
            )
        )
        ** 5,
        11.7584,
    )
    return _bool_signal(left < right)


def _alpha096(library):
    first = _ts_rank(
        _decay_linear(
            _correlation(_rank(_vwap(library)), _rank(library.volume), 3.83878),
            4.16783,
        ),
        8.38151,
    )
    second = _ts_rank(
        _decay_linear(
            _ts_argmax(
                _correlation(
                    _ts_rank(library.close, 7.45404),
                    _ts_rank(_adv(library, 60), 4.13242),
                    3.65459,
                ),
                12.6556,
            ),
            14.0365,
        ),
        13.4143,
    )
    return -np.maximum(first, second)


def _alpha097(library):
    vwap = _vwap(library)
    first = _rank(
        _decay_linear(
            _delta(
                _indneutralize(
                    library,
                    library.low * 0.721001 + vwap * (1 - 0.721001),
                    "industry",
                ),
                3.3705,
            ),
            20.4523,
        )
    )
    second = _ts_rank(
        _decay_linear(
            _ts_rank(
                _correlation(
                    _ts_rank(library.low, 7.87871),
                    _ts_rank(_adv(library, 60), 17.255),
                    4.97547,
                ),
                18.5925,
            ),
            15.7152,
        ),
        6.71659,
    )
    return -(first - second)


def _alpha098(library):
    vwap = _vwap(library)
    first = _rank(
        _decay_linear(
            _correlation(vwap, _ts_sum(_adv(library, 5), 26.4719), 4.58418),
            7.18088,
        )
    )
    second = _rank(
        _decay_linear(
            _ts_rank(
                _ts_argmin(
                    _correlation(
                        _rank(library.open),
                        _rank(_adv(library, 15)),
                        20.8187,
                    ),
                    8.62571,
                ),
                6.95668,
            ),
            8.07206,
        )
    )
    return first - second


def _alpha099(library):
    left = _rank(
        _correlation(
            _ts_sum((library.high + library.low) / 2.0, 19.8975),
            _ts_sum(_adv(library, 60), 19.8975),
            8.8136,
        )
    )
    right = _rank(_correlation(library.low, library.volume, 6.28259))
    return _bool_signal(left < right, -1.0)


def _alpha100(library):
    inner = _safe_divide(
        ((library.close - library.low) - (library.high - library.close)) * library.volume,
        library.high - library.low,
    )
    first = _scale(
        _indneutralize(
            library,
            _indneutralize(library, _rank(inner), "subindustry"),
            "subindustry",
        )
    )
    second = _scale(
        _indneutralize(
            library,
            _correlation(library.close, _rank(_adv(library, 20)), 5)
            - _rank(_ts_argmin(library.close, 30)),
            "subindustry",
        )
    )
    return -(1.5 * first - second) * _safe_divide(
        library.volume, _adv(library, 20)
    )


def _alpha101(library):
    return _safe_divide(
        library.close - library.open,
        library.high - library.low + 0.001,
        epsilon=0.0,
    )


_ALPHA_CALCULATORS: dict[int, Callable[[WorldQuantAlpha101Library], pd.DataFrame]] = {
    number: globals()[f"_alpha{number:03d}"] for number in range(1, 102)
}


def _add_alpha_method(number: int, calculator: Callable) -> None:
    name = f"alpha{number:03d}"

    def factor(self: WorldQuantAlpha101Library, _calculator=calculator):
        return _calculator(self)

    factor.__name__ = name
    factor.__doc__ = f"WorldQuant Formulaic Alpha #{number:03d}。"
    setattr(WorldQuantAlpha101Library, name, factor)


for _number, _calculator in _ALPHA_CALCULATORS.items():
    _add_alpha_method(_number, _calculator)


__all__ = ["WorldQuantAlpha101Library"]
