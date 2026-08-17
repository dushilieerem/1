"""国泰君安 Alpha191 因子库。

本模块把公开的国泰君安/聚宽 Alpha191 公式独立复算为 SVQuant 的
``FactorLibrary``。实现只依赖 Pandas/NumPy，输入输出均为 ``日期×标的``
宽表，不依赖聚宽运行时、账号或因子值。

实现约定：

* 公开因子名为 ``alpha191_001`` … ``alpha191_191``，避免与现有
  WorldQuant ``alpha001`` … ``alpha101`` 重名；
* 必需字段为 ``open``、``high``、``low``、``close``、``volume``；
  ``amount``/``vwap`` 为可选字段，缺失时分别回退到 ``close * volume``
  和典型价格；
* 公式中的小数窗口按向下取整，SMA 使用国泰君安常见的递推平滑
  ``alpha=M/N``；
* Alpha149/75/182 等需要基准指数的公式优先读取
  ``benchmark_close``/``benchmark_open`` 或 CSI300 指数；若没有基准，
  使用全股票等权均值作为明确标注的研究代理，保证库仍可在 OHLCV 面板上运行；
* 零分母返回缺失值，所有结果保持输入索引和标的列，不使用未来数据。

公式来源：JoinQuant 公开因子文档（https://www.joinquant.com/help/api/help#factor_values）
及公开 Alpha191 公式整理（https://github.com/Daic115/alpha191）。本文件为
SVQuant 的独立 Pandas/NumPy 实现，不包含第三方运行时或受限因子值。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from quantcore import FactorLibrary


EPSILON = 1e-12


def _window(value: int | float) -> int:
    """把公式中的窗口转成至少为 1 的整数。"""
    return max(1, int(np.floor(float(value))))


def _delay(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    return frame.shift(_window(value))


def _delta(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    return frame.diff(_window(value))


def _ts_sum(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).sum()


def _ts_mean(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).mean()


def _ts_std(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).std()


def _ts_min(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).min()


def _ts_max(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).max()


def _ts_rank(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    # pandas rolling.rank 返回每个窗口最后一个观测的秩，正好对应 TSRANK。
    try:
        return frame.rolling(size, min_periods=size).rank(pct=True)
    except AttributeError:  # pragma: no cover - 兼容旧版 pandas
        return frame.rolling(size, min_periods=size).apply(
            lambda values: float(pd.Series(values).rank(pct=True).iloc[-1]),
            raw=True,
        )


def _rank(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rank(axis=1, method="average", pct=True)


def _corr(left: pd.DataFrame, right: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return left.rolling(size, min_periods=size).corr(right).replace(
        [np.inf, -np.inf], np.nan
    )


def _cov(left: pd.DataFrame, right: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return left.rolling(size, min_periods=size).cov(right).replace(
        [np.inf, -np.inf], np.nan
    )


def _sma(frame: pd.DataFrame, n: int | float, m: int | float) -> pd.DataFrame:
    """国泰君安 SMA(X,N,M)：递推平滑，alpha=M/N。"""
    size = _window(n)
    smooth = min(max(float(m) / float(size), 0.0), 1.0)
    return frame.ewm(alpha=smooth, adjust=False).mean()


def _decay_linear(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    weights = np.arange(1, size + 1, dtype=float)
    weights /= weights.sum()
    return frame.rolling(size, min_periods=size).apply(
        lambda values: float(np.dot(weights, values)), raw=True
    )


def _wma(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    weights = np.array([0.9 ** (size - 1 - i) for i in range(size)], dtype=float)
    weights /= weights.sum()
    return frame.rolling(size, min_periods=size).apply(
        lambda values: float(np.dot(weights, values)), raw=True
    )


def _ts_product(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).apply(np.prod, raw=True)


def _ts_argmin(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).apply(
        lambda values: float(np.argmin(values) + 1), raw=True
    )


def _ts_argmax(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).apply(
        lambda values: float(np.argmax(values) + 1), raw=True
    )


def _lowday(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).apply(
        lambda values: float(np.argmin(values[::-1])), raw=True
    )


def _highday(frame: pd.DataFrame, value: int | float) -> pd.DataFrame:
    size = _window(value)
    return frame.rolling(size, min_periods=size).apply(
        lambda values: float(np.argmax(values[::-1])), raw=True
    )


def _count(condition: pd.DataFrame, value: int | float) -> pd.DataFrame:
    return _ts_sum(condition.astype(float), value)


def _sumif(frame: pd.DataFrame, value: int | float, condition: pd.DataFrame) -> pd.DataFrame:
    return frame.where(condition, other=0.0).rolling(
        _window(value), min_periods=_window(value)
    ).sum()


def _regbeta(
    dependent: pd.DataFrame,
    independent: pd.DataFrame | np.ndarray,
    value: int | float,
) -> pd.DataFrame:
    """滚动回归斜率，支持确定性序列或逐标的自变量面板。"""
    size = _window(value)
    if isinstance(independent, np.ndarray):
        x = np.asarray(independent, dtype=float)
        centered = x - x.mean()
        denominator = float(np.dot(centered, centered))
        if denominator <= EPSILON:
            return pd.DataFrame(np.nan, index=dependent.index, columns=dependent.columns)
        return dependent.rolling(size, min_periods=size).apply(
            lambda values: float(np.dot(centered, values - values.mean()) / denominator),
            raw=True,
        )
    # FILTER 语义会在窗口内留下缺失行；滚动回归按有效配对观测计算，
    # 至少需要两个有效点，而不是把 252 个自然日都强制要求为非缺失。
    covariance = dependent.rolling(size, min_periods=2).cov(independent)
    variance = independent.rolling(size, min_periods=2).var()
    return covariance.div(variance.where(variance.abs() > EPSILON))


def _safe_divide(
    numerator: pd.DataFrame | float | int,
    denominator: pd.DataFrame | float | int,
    epsilon: float = EPSILON,
) -> pd.DataFrame:
    if np.isscalar(denominator):
        denominator_value = float(denominator)
        if abs(denominator_value) <= epsilon:
            return pd.DataFrame(np.nan, index=numerator.index, columns=numerator.columns) if isinstance(numerator, pd.DataFrame) else pd.DataFrame(np.nan)
        if isinstance(numerator, pd.DataFrame):
            return numerator / denominator_value
        return pd.DataFrame(numerator / denominator_value)
    if not isinstance(numerator, pd.DataFrame):
        numerator = pd.DataFrame(numerator, index=denominator.index, columns=denominator.columns)
    valid = denominator.abs() > epsilon if epsilon else denominator != 0
    return numerator.div(denominator.where(valid))


def _elementwise_max(left: pd.DataFrame, right: pd.DataFrame | float | int) -> pd.DataFrame:
    if np.isscalar(right):
        return left.clip(lower=float(right))
    return pd.DataFrame(
        np.maximum(left.to_numpy(dtype=float), right.to_numpy(dtype=float)),
        index=left.index,
        columns=left.columns,
    )


def _elementwise_min(left: pd.DataFrame, right: pd.DataFrame | float | int) -> pd.DataFrame:
    if np.isscalar(right):
        return left.clip(upper=float(right))
    return pd.DataFrame(
        np.minimum(left.to_numpy(dtype=float), right.to_numpy(dtype=float)),
        index=left.index,
        columns=left.columns,
    )


def _row_max(frame: pd.DataFrame) -> pd.Series:
    return frame.max(axis=1)


def _row_min(frame: pd.DataFrame) -> pd.Series:
    return frame.min(axis=1)


def _broadcast_series(series: pd.Series, template: pd.DataFrame) -> pd.DataFrame:
    """按日期把一条序列复制到每个标的列。"""
    return pd.DataFrame(
        np.broadcast_to(series.reindex(template.index).to_numpy()[:, None], template.shape),
        index=template.index,
        columns=template.columns,
    )


def _signed_power(base: pd.DataFrame, exponent: pd.DataFrame | float | int) -> pd.DataFrame:
    if np.isscalar(exponent):
        return np.sign(base) * np.power(base.abs(), float(exponent))
    return np.sign(base) * np.power(base.abs(), exponent)


def _align_result(result: Any, template: pd.DataFrame) -> pd.DataFrame:
    """把标量/Series/数组结果对齐为面板宽表，并清理无穷值。"""
    if result is None:
        output = pd.DataFrame(np.nan, index=template.index, columns=template.columns)
    elif isinstance(result, pd.DataFrame):
        output = result.reindex(index=template.index, columns=template.columns)
    elif isinstance(result, pd.Series):
        if result.index.equals(template.index):
            output = pd.concat({column: result for column in template.columns}, axis=1)
            output = output.reindex(columns=template.columns)
        else:
            output = pd.DataFrame(result, index=template.index, columns=template.columns)
    else:
        array = np.asarray(result)
        if array.ndim == 0:
            output = pd.DataFrame(float(array), index=template.index, columns=template.columns)
        else:
            output = pd.DataFrame(array, index=template.index, columns=template.columns)
    return output.replace([np.inf, -np.inf], np.nan)


class GTJAAlpha191Library(FactorLibrary):
    """国泰君安 Alpha191 的 SVQuant 原生面板实现。"""

    author = "SVQuant"

    def _optional_field(self, name: str) -> pd.DataFrame | None:
        if name in self.fields:
            return self[name]
        return None

    def _cached(self, name: str, factory: Callable[[], Any]) -> Any:
        panel_id = id(self._panel)
        if getattr(self, "_cache_panel_id", None) != panel_id:
            self._cache_panel_id = panel_id
            self._factor_cache: dict[str, Any] = {}
        if name not in self._factor_cache:
            self._factor_cache[name] = factory()
        return self._factor_cache[name]

    def _amount(self) -> pd.DataFrame:
        return self._cached(
            "amount",
            lambda: self._optional_field("amount")
            if self._optional_field("amount") is not None
            else self.close * self.volume,
        )

    def _vwap(self) -> pd.DataFrame:
        def build() -> pd.DataFrame:
            direct = self._optional_field("vwap")
            if direct is not None:
                return direct
            amount = self._optional_field("amount")
            if amount is not None:
                return _safe_divide(amount, self.volume)
            return (self.high + self.low + self.close) / 3.0

        return self._cached("vwap", build)

    def _returns(self) -> pd.DataFrame:
        return self._cached("returns", lambda: self.close.pct_change())

    def _benchmark(self) -> tuple[pd.Series, pd.Series]:
        def build() -> tuple[pd.Series, pd.Series]:
            close = self._optional_field("benchmark_close")
            open_ = self._optional_field("benchmark_open")
            if close is not None:
                close_series = close.iloc[:, 0] if close.shape[1] else self.close.mean(axis=1)
            else:
                try:
                    close_series = self.csi300.close
                    if isinstance(close_series, pd.DataFrame):
                        close_series = close_series.iloc[:, 0]
                except (AttributeError, KeyError):
                    close_series = self.close.mean(axis=1)
            if open_ is not None:
                open_series = open_.iloc[:, 0] if open_.shape[1] else self.open.mean(axis=1)
            else:
                try:
                    open_series = self.csi300.open
                    if isinstance(open_series, pd.DataFrame):
                        open_series = open_series.iloc[:, 0]
                except (AttributeError, KeyError):
                    open_series = self.open.mean(axis=1)
            return close_series.reindex(self.close.index), open_series.reindex(self.close.index)

        return self._cached("benchmark", build)

    def _independent_group(self, frame: pd.DataFrame, level: str) -> pd.DataFrame:
        groups = None
        for name in (level, f"{level}_code"):
            groups = self._optional_field(name)
            if groups is not None:
                break
        if groups is None:
            return frame.sub(frame.mean(axis=1), axis=0)
        groups = groups.reindex(index=frame.index, columns=frame.columns)
        result = frame.copy()
        for label in pd.unique(groups.to_numpy().ravel()):
            if pd.isna(label):
                continue
            mask = groups.eq(label)
            group_mean = frame.where(mask).mean(axis=1)
            result = result.where(~mask, frame.sub(group_mean, axis=0))
        missing = groups.isna()
        if missing.any().any():
            result = result.where(~missing, frame.sub(frame.where(missing).mean(axis=1), axis=0))
        return result


def _alpha001(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_corr(_rank(_delta(np.log(lib.volume), 1)), _rank(_safe_divide(lib.close - lib.open, lib.open)), 6)


def _alpha002(lib: GTJAAlpha191Library) -> pd.DataFrame:
    numerator = (lib.close - lib.low) - (lib.high - lib.close)
    return -_delta(_safe_divide(numerator, lib.high - lib.low), 1)


def _alpha003(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    up = lib.close > previous
    down = lib.close < previous
    part_up = lib.close - _elementwise_min(lib.low, previous)
    part_down = lib.close - _elementwise_max(lib.high, previous)
    part = part_up.where(up, part_down.where(down, 0.0))
    return _ts_sum(part, 6)


def _alpha004(lib: GTJAAlpha191Library) -> pd.DataFrame:
    mean_long = _ts_mean(lib.close, 8)
    std_long = _ts_std(lib.close, 8)
    mean_short = _ts_mean(lib.close, 2)
    volume_ratio = _safe_divide(lib.volume, _ts_mean(lib.volume, 20))
    condition = (mean_long + std_long < mean_short)
    condition_mid = mean_short < mean_long - std_long
    return pd.DataFrame(
        np.where(condition, -1.0, np.where(condition_mid, 1.0, np.where(volume_ratio >= 1.0, 1.0, -1.0))),
        index=lib.close.index,
        columns=lib.close.columns,
    )


def _alpha005(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_ts_max(_corr(_ts_rank(lib.volume, 5), _ts_rank(lib.high, 5), 5), 3)


def _alpha006(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(np.sign(_delta(lib.open * 0.85 + lib.high * 0.15, 4)))


def _alpha007(lib: GTJAAlpha191Library) -> pd.DataFrame:
    spread = lib._vwap() - lib.close
    return (_rank(_ts_max(spread, 3)) + _rank(_ts_min(spread, 3))) * _rank(_delta(lib.volume, 3))


def _alpha008(lib: GTJAAlpha191Library) -> pd.DataFrame:
    weighted = (lib.high + lib.low) / 2.0 * 0.2 + lib._vwap() * 0.8
    return _rank(-_delta(weighted, 4))


def _alpha009(lib: GTJAAlpha191Library) -> pd.DataFrame:
    midpoint_change = (lib.high + lib.low) / 2.0 - (_delay(lib.high, 1) + _delay(lib.low, 1)) / 2.0
    return _sma(_safe_divide(midpoint_change * (lib.high - lib.low), lib.volume), 7, 2)


def _alpha010(lib: GTJAAlpha191Library) -> pd.DataFrame:
    returns = lib._returns()
    selected = _ts_std(returns, 20).where(returns < 0, lib.close)
    return _rank(_ts_max(selected ** 2, 5))


def _alpha011(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_sum(_safe_divide((2 * lib.close - lib.low - lib.high) * lib.volume, lib.high - lib.low), 6)


def _alpha012(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _rank(lib.open - _ts_sum(lib._vwap(), 10) / 10.0) * _rank((lib.close - lib._vwap()).abs())


def _alpha013(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return np.sqrt(lib.high * lib.low) - lib._vwap()


def _alpha014(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return lib.close - _delay(lib.close, 5)


def _alpha015(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(lib.open, _delay(lib.close, 1)) - 1.0


def _alpha016(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_ts_max(_rank(_corr(_rank(lib.volume), _rank(lib._vwap()), 5)), 5)


def _alpha017(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _signed_power(_rank(lib._vwap() - _ts_max(lib._vwap(), 15)), _delta(lib.close, 5))


def _alpha018(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(lib.close, _delay(lib.close, 5))


def _alpha019(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 5)
    down = lib.close < previous
    up = lib.close > previous
    return _safe_divide(lib.close - previous, previous).where(down, _safe_divide(lib.close - previous, lib.close).where(up, 0.0))


def _alpha020(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 6)
    return _safe_divide(lib.close - previous, previous) * 100.0


def _alpha021(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _regbeta(_ts_mean(lib.close, 6), np.arange(1, 7, dtype=float), 6)


def _alpha022(lib: GTJAAlpha191Library) -> pd.DataFrame:
    mean6 = _ts_mean(lib.close, 6)
    deviation = _safe_divide(lib.close - mean6, mean6)
    return _sma(deviation - _delay(deviation, 3), 12, 1)


def _alpha023(lib: GTJAAlpha191Library) -> pd.DataFrame:
    up = _ts_std(lib.close, 20).where(lib.close > _delay(lib.close, 1), 0.0)
    down = _ts_std(lib.close, 20).where(lib.close <= _delay(lib.close, 1), 0.0)
    smooth_up = _sma(up, 20, 1)
    smooth_down = _sma(down, 20, 1)
    return 100.0 * _safe_divide(smooth_up, smooth_up + smooth_down)


def _alpha024(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _sma(lib.close - _delay(lib.close, 5), 5, 1)


def _alpha025(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_delta(lib.close, 7) * (1.0 - _rank(_decay_linear(_safe_divide(lib.volume, _ts_mean(lib.volume, 20)), 9)))) * (1.0 + _rank(_ts_sum(lib._returns(), 250)))


def _alpha026(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_sum(lib.close, 7) / 7.0 - lib.close + _corr(lib._vwap(), _delay(lib.close, 5), 230)


def _alpha027(lib: GTJAAlpha191Library) -> pd.DataFrame:
    momentum = _safe_divide(lib.close - _delay(lib.close, 3), _delay(lib.close, 3)) * 100.0 + _safe_divide(lib.close - _delay(lib.close, 6), _delay(lib.close, 6)) * 100.0
    return _wma(momentum, 12)


def _alpha028(lib: GTJAAlpha191Library) -> pd.DataFrame:
    lower = _ts_min(lib.low, 9)
    spread = _ts_max(lib.high, 9) - lower
    kd = _safe_divide(lib.close - lower, spread) * 100.0
    smooth = _sma(kd, 3, 1)
    return 3.0 * smooth - 2.0 * _sma(smooth, 3, 1)


def _alpha029(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(lib.close - _delay(lib.close, 6), _delay(lib.close, 6)) * lib.volume


def _alpha030(lib: GTJAAlpha191Library) -> pd.DataFrame:
    # 原始公式需要 Fama-French 市场因子；当前面板没有该数据时返回缺失值。
    return None


def _alpha031(lib: GTJAAlpha191Library) -> pd.DataFrame:
    mean12 = _ts_mean(lib.close, 12)
    return _safe_divide(lib.close - mean12, mean12) * 100.0


def _alpha032(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_ts_sum(_rank(_corr(_rank(lib.high), _rank(lib.volume), 3)), 3)


def _alpha033(lib: GTJAAlpha191Library) -> pd.DataFrame:
    low5 = _ts_min(lib.low, 5)
    return (-low5 + _delay(low5, 5)) * _rank((_ts_sum(lib._returns(), 240) - _ts_sum(lib._returns(), 20)) / 220.0) * _ts_rank(lib.volume, 5)


def _alpha034(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(_ts_mean(lib.close, 12), lib.close)


def _alpha035(lib: GTJAAlpha191Library) -> pd.DataFrame:
    left = _rank(_decay_linear(_delta(lib.open, 1), 15))
    right = _rank(_decay_linear(_corr(lib.volume, lib.open, 17), 7))
    return _elementwise_min(left, right)


def _alpha036(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _rank(_ts_sum(_corr(_rank(lib.volume), _rank(lib._vwap()), 6), 2))


def _alpha037(lib: GTJAAlpha191Library) -> pd.DataFrame:
    inner = _ts_sum(lib.open, 5) * _ts_sum(lib._returns(), 5)
    return -_rank(inner - _delay(inner, 10))


def _alpha038(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return (-_delta(lib.high, 2)).where(_ts_mean(lib.high, 20) < lib.high, 0.0)


def _alpha039(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(_decay_linear(_delta(lib.close, 2), 8))
    second = _rank(_decay_linear(_corr(lib._vwap() * 0.3 + lib.open * 0.7, _ts_sum(_ts_mean(lib.volume, 180), 37), 14), 12))
    return first - second


def _alpha040(lib: GTJAAlpha191Library) -> pd.DataFrame:
    up = lib.volume.where(lib.close > _delay(lib.close, 1), 0.0)
    down = lib.volume.where(lib.close <= _delay(lib.close, 1), 0.0)
    return _safe_divide(_ts_sum(up, 26), _ts_sum(down, 26)) * 100.0


def _alpha041(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_ts_max(_delta(lib._vwap(), 3), 5))


def _alpha042(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_ts_std(lib.high, 10)) * _corr(lib.high, lib.volume, 10)


def _alpha043(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    signed_volume = lib.volume.where(lib.close > previous, (-lib.volume).where(lib.close < previous, 0.0))
    return _ts_sum(signed_volume, 6)


def _alpha044(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_rank(_decay_linear(_corr(lib.low, _ts_mean(lib.volume, 10), 7), 6), 4) + _ts_rank(_decay_linear(_delta(lib._vwap(), 3), 10), 15)


def _alpha045(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _rank(_delta(lib.close * 0.6 + lib.open * 0.4, 1)) * _rank(_corr(lib._vwap(), _ts_mean(lib.volume, 150), 15))


def _alpha046(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return (_ts_mean(lib.close, 3) + _ts_mean(lib.close, 6) + _ts_mean(lib.close, 12) + _ts_mean(lib.close, 24)) / (4.0 * lib.close)


def _alpha047(lib: GTJAAlpha191Library) -> pd.DataFrame:
    spread = _ts_max(lib.high, 6) - _ts_min(lib.low, 6)
    return _sma(_safe_divide(_ts_max(lib.high, 6) - lib.close, spread) * 100.0, 9, 1)


def _alpha048(lib: GTJAAlpha191Library) -> pd.DataFrame:
    signed = np.sign(lib.close - _delay(lib.close, 1)) + np.sign(_delay(lib.close, 1) - _delay(lib.close, 2)) + np.sign(_delay(lib.close, 2) - _delay(lib.close, 3))
    return -_rank(signed) * _safe_divide(_ts_sum(lib.volume, 5), _ts_sum(lib.volume, 20))


def _tr_parts(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _elementwise_max((lib.high - _delay(lib.high, 1)).abs(), (lib.low - _delay(lib.low, 1)).abs())


def _alpha049(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous_sum = _delay(lib.high, 1) + _delay(lib.low, 1)
    current_sum = lib.high + lib.low
    movement = _tr_parts(lib)
    down = movement.where(current_sum < previous_sum, 0.0)
    up = movement.where(current_sum > previous_sum, 0.0)
    return _safe_divide(_ts_sum(down, 12), _ts_sum(down, 12) + _ts_sum(up, 12))


def _alpha050(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous_sum = _delay(lib.high, 1) + _delay(lib.low, 1)
    current_sum = lib.high + lib.low
    movement = _tr_parts(lib)
    up = movement.where(current_sum > previous_sum, 0.0)
    down = movement.where(current_sum < previous_sum, 0.0)
    return _safe_divide(_ts_sum(up, 12) - _ts_sum(down, 12), _ts_sum(up, 12) + _ts_sum(down, 12))


def _alpha051(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous_sum = _delay(lib.high, 1) + _delay(lib.low, 1)
    current_sum = lib.high + lib.low
    movement = _tr_parts(lib)
    up = movement.where(current_sum > previous_sum, 0.0)
    down = movement.where(current_sum < previous_sum, 0.0)
    return _safe_divide(_ts_sum(up, 12), _ts_sum(up, 12) + _ts_sum(down, 12))


def _alpha052(lib: GTJAAlpha191Library) -> pd.DataFrame:
    typical = (lib.high + lib.low + lib.close) / 3.0
    return _safe_divide(_ts_sum(_elementwise_max(lib.high - _delay(typical, 1), 0.0), 26), _ts_sum(_elementwise_max(_delay(typical, 1) - lib.low, 0.0), 26)) * 100.0


def _alpha053(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _count(lib.close > _delay(lib.close, 1), 12) / 12.0 * 100.0


def _alpha054(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _rank(_ts_std((lib.close - lib.open).abs(), 5) + (lib.close - lib.open) + _corr(lib.close, lib.open, 10))


def _alpha055(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous_close = _delay(lib.close, 1)
    previous_open = _delay(lib.open, 1)
    a = (lib.high - previous_close).abs()
    b = (lib.low - previous_close).abs()
    c = (lib.high - _delay(lib.low, 1)).abs()
    d = (previous_close - previous_open).abs()
    condition_a = (a > b) & (a > c)
    condition_b = (b > c) & (b > a)
    denominator = pd.DataFrame(
        np.where(condition_a, a + b / 2.0 + d / 4.0, np.where(condition_b, b + a / 2.0 + d / 4.0, c + d / 4.0)),
        index=lib.close.index,
        columns=lib.close.columns,
    )
    part = 16.0 * (lib.close + (lib.close - lib.open) / 2.0 - previous_open)
    return _ts_sum(_safe_divide(part * _elementwise_max(a, b), denominator), 20)


def _alpha056(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(lib.open - _ts_min(lib.open, 12))
    second = _rank(_rank(_corr(_ts_sum((lib.high + lib.low) / 2.0, 19), _ts_sum(_ts_mean(lib.volume, 40), 19), 13)) ** 5)
    return pd.DataFrame(np.where(first < second, 1.0, -1.0), index=lib.close.index, columns=lib.close.columns)


def _alpha057(lib: GTJAAlpha191Library) -> pd.DataFrame:
    spread = _ts_max(lib.high, 9) - _ts_min(lib.low, 9)
    kd = _safe_divide(lib.close - _ts_min(lib.low, 9), spread) * 100.0
    return _sma(kd, 3, 1)


def _alpha058(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _count(lib.close > _delay(lib.close, 1), 20) / 20.0 * 100.0


def _alpha059(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    up = lib.close > previous
    down = lib.close < previous
    part = (lib.close - _elementwise_min(lib.low, previous)).where(up, (lib.close - _elementwise_max(lib.high, previous)).where(down, 0.0))
    return _ts_sum(part, 20)


def _alpha060(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_sum(_safe_divide(((lib.close - lib.low) - (lib.high - lib.close)) * lib.volume, lib.high - lib.low), 20)


def _alpha061(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(_decay_linear(_delta(lib._vwap(), 1), 12))
    second = _rank(_decay_linear(_rank(_corr(lib.low, _ts_mean(lib.volume, 80), 8)), 17))
    return -_elementwise_max(first, second)


def _alpha062(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_corr(lib.high, _rank(lib.volume), 5)


def _alpha063(lib: GTJAAlpha191Library) -> pd.DataFrame:
    change = lib.close - _delay(lib.close, 1)
    return _safe_divide(_sma(_elementwise_max(change, 0.0), 6, 1), _sma(change.abs(), 6, 1)) * 100.0


def _alpha064(lib: GTJAAlpha191Library) -> pd.DataFrame:
    left = _rank(_decay_linear(_corr(_rank(lib._vwap()), _rank(lib.volume), 4), 4))
    right = _rank(_decay_linear(_ts_max(_corr(_rank(lib.close), _rank(_ts_mean(lib.volume, 60)), 4), 13), 14))
    return -_elementwise_max(left, right)


def _alpha065(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(_ts_mean(lib.close, 6), lib.close)


def _alpha066(lib: GTJAAlpha191Library) -> pd.DataFrame:
    mean6 = _ts_mean(lib.close, 6)
    return _safe_divide(lib.close - mean6, mean6) * 100.0


def _alpha067(lib: GTJAAlpha191Library) -> pd.DataFrame:
    change = lib.close - _delay(lib.close, 1)
    return _safe_divide(_sma(_elementwise_max(change, 0.0), 24, 1), _sma(change.abs(), 24, 1)) * 100.0


def _alpha068(lib: GTJAAlpha191Library) -> pd.DataFrame:
    midpoint_change = (lib.high + lib.low) / 2.0 - (_delay(lib.high, 1) + _delay(lib.low, 1)) / 2.0
    return _sma(_safe_divide(midpoint_change * (lib.high - lib.low), lib.volume), 15, 2) * 100.0


def _alpha069(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous_open = _delay(lib.open, 1)
    dtm = _elementwise_max(lib.high - lib.open, lib.open - previous_open).where(lib.open > previous_open, 0.0)
    dbm = _elementwise_max(lib.open - lib.low, lib.open - previous_open).where(lib.open < previous_open, 0.0)
    sdtm = _ts_sum(dtm, 20)
    sdbm = _ts_sum(dbm, 20)
    return _safe_divide(sdtm - sdbm, sdtm).where(sdtm > sdbm, _safe_divide(sdtm - sdbm, sdbm).where(sdtm < sdbm, 0.0))


def _alpha070(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_std(lib._amount(), 6)


def _alpha071(lib: GTJAAlpha191Library) -> pd.DataFrame:
    mean24 = _ts_mean(lib.close, 24)
    return _safe_divide(lib.close - mean24, mean24) * 100.0


def _alpha072(lib: GTJAAlpha191Library) -> pd.DataFrame:
    spread = _ts_max(lib.high, 6) - _ts_min(lib.low, 6)
    return _sma(_safe_divide(_ts_max(lib.high, 6) - lib.close, spread) * 100.0, 15, 1)


def _alpha073(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _ts_rank(_decay_linear(_decay_linear(_corr(lib.close, lib.volume, 10), 16), 4), 5)
    second = _rank(_decay_linear(_corr(lib._vwap(), _ts_mean(lib.volume, 30), 4), 3))
    return -(first - second)


def _alpha074(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(_corr(_ts_sum(lib.low * 0.35 + lib._vwap() * 0.65, 20), _ts_sum(_ts_mean(lib.volume, 40), 20), 7))
    second = _rank(_corr(_rank(lib._vwap()), _rank(lib.volume), 6))
    return first + second


def _alpha075(lib: GTJAAlpha191Library) -> pd.DataFrame:
    benchmark_close, benchmark_open = lib._benchmark()
    stock_up_benchmark_down = (lib.close > lib.open).mul(benchmark_close < benchmark_open, axis=0)
    benchmark_down = pd.DataFrame(
        np.broadcast_to((benchmark_close < benchmark_open).to_numpy()[:, None], lib.close.shape),
        index=lib.close.index,
        columns=lib.close.columns,
    )
    return _safe_divide(_count(stock_up_benchmark_down, 50), _count(benchmark_down, 50))


def _alpha076(lib: GTJAAlpha191Library) -> pd.DataFrame:
    scaled = _safe_divide((lib.close / _delay(lib.close, 1) - 1.0).abs(), lib.volume)
    return _safe_divide(_ts_std(scaled, 20), _ts_mean(scaled, 20))


def _alpha077(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(_decay_linear((lib.high + lib.low) / 2.0 - lib._vwap(), 20))
    second = _rank(_decay_linear(_corr((lib.high + lib.low) / 2.0, _ts_mean(lib.volume, 40), 3), 6))
    return _elementwise_min(first, second)


def _alpha078(lib: GTJAAlpha191Library) -> pd.DataFrame:
    typical = (lib.high + lib.low + lib.close) / 3.0
    mean12 = _ts_mean(typical, 12)
    return _safe_divide(typical - mean12, _ts_mean((lib.close - mean12).abs(), 12) * 0.015)


def _alpha079(lib: GTJAAlpha191Library) -> pd.DataFrame:
    change = lib.close - _delay(lib.close, 1)
    return _safe_divide(_sma(_elementwise_max(change, 0.0), 12, 1), _sma(change.abs(), 12, 1)) * 100.0


def _alpha080(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(lib.volume - _delay(lib.volume, 5), _delay(lib.volume, 5)) * 100.0


def _alpha081(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _sma(lib.volume, 21, 2)


def _alpha082(lib: GTJAAlpha191Library) -> pd.DataFrame:
    spread = _ts_max(lib.high, 6) - _ts_min(lib.low, 6)
    return _sma(_safe_divide(_ts_max(lib.high, 6) - lib.close, spread) * 100.0, 20, 1)


def _alpha083(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_cov(_rank(lib.high), _rank(lib.volume), 5))


def _alpha084(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    signed = lib.volume.where(lib.close > previous, (-lib.volume).where(lib.close < previous, 0.0))
    return _ts_sum(signed, 20)


def _alpha085(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_rank(_safe_divide(lib.volume, _ts_mean(lib.volume, 20)), 20) * _ts_rank(-_delta(lib.close, 7), 8)


def _alpha086(lib: GTJAAlpha191Library) -> pd.DataFrame:
    value = _safe_divide(_delay(lib.close, 20) - _delay(lib.close, 10), 10.0) - _safe_divide(_delay(lib.close, 10) - lib.close, 10.0)
    return pd.DataFrame(np.where(value > 0.25, -1.0, np.where(value < 0.0, 1.0, -(lib.close - _delay(lib.close, 1)))), index=lib.close.index, columns=lib.close.columns)


def _alpha087(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(_decay_linear(_delta(lib._vwap(), 4), 7))
    second = _ts_rank(_decay_linear(_safe_divide(lib.high - lib._vwap(), lib.open - (lib.high + lib.low) / 2.0), 11), 7)
    return -(first + second)


def _alpha088(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(lib.close - _delay(lib.close, 20), _delay(lib.close, 20))


def _alpha089(lib: GTJAAlpha191Library) -> pd.DataFrame:
    fast = _sma(lib.close, 13, 2)
    slow = _sma(lib.close, 27, 2)
    diff = fast - slow
    return 2.0 * (diff - _sma(diff, 10, 2))


def _alpha090(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_corr(_rank(lib._vwap()), _rank(lib.volume), 5))


def _alpha091(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(lib.close - _ts_max(lib.close, 5)) * _rank(_corr(_ts_mean(lib.volume, 40), lib.low, 5))


def _alpha092(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(_decay_linear(_delta(lib.close * 0.35 + lib._vwap() * 0.65, 2), 3))
    second = _ts_rank(_decay_linear(_corr(_ts_mean(lib.volume, 180), lib.close, 13).abs(), 5), 15)
    return -_elementwise_max(first, second)


def _alpha093(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous_open = _delay(lib.open, 1)
    part = _elementwise_max(lib.open - lib.low, lib.open - previous_open).where(lib.open < previous_open, 0.0)
    return _ts_sum(part, 20)


def _alpha094(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    signed = lib.volume.where(lib.close > previous, (-lib.volume).where(lib.close < previous, 0.0))
    return _ts_sum(signed, 30)


def _alpha095(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_std(lib._amount(), 20)


def _alpha096(lib: GTJAAlpha191Library) -> pd.DataFrame:
    spread = _ts_max(lib.high, 9) - _ts_min(lib.low, 9)
    kd = _safe_divide(lib.close - _ts_min(lib.low, 9), spread) * 100.0
    return _sma(_sma(kd, 3, 1), 3, 1)


def _alpha097(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_std(lib.volume, 10)


def _alpha098(lib: GTJAAlpha191Library) -> pd.DataFrame:
    mean100 = _ts_mean(lib.close, 100)
    condition = _safe_divide(_delta(mean100, 100), _delay(lib.close, 100)) <= 0.05
    return (-(lib.close - _ts_min(lib.close, 100))).where(condition, -_delta(lib.close, 3))


def _alpha099(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_cov(_rank(lib.close), _rank(lib.volume), 5))


def _alpha100(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_std(lib.volume, 20)


def _alpha101(lib: GTJAAlpha191Library) -> pd.DataFrame:
    rank1 = _rank(_corr(lib.close, _ts_sum(_ts_mean(lib.volume, 30), 37), 15))
    rank2 = _rank(_corr(_rank(lib.high * 0.1 + lib._vwap() * 0.9), _rank(lib.volume), 11))
    return pd.DataFrame(np.where(rank1 < rank2, -1.0, 1.0), index=lib.close.index, columns=lib.close.columns)


def _alpha102(lib: GTJAAlpha191Library) -> pd.DataFrame:
    change = lib.volume - _delay(lib.volume, 1)
    return _safe_divide(_sma(_elementwise_max(change, 0.0), 6, 1), _sma(change.abs(), 6, 1)) * 100.0


def _alpha103(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return (20.0 - _lowday(lib.low, 20)) / 20.0 * 100.0


def _alpha104(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_delta(_corr(lib.high, lib.volume, 5), 5) * _rank(_ts_std(lib.close, 20))


def _alpha105(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _corr(_rank(lib.open), _rank(lib.volume), 10)


def _alpha106(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return lib.close - _delay(lib.close, 20)


def _alpha107(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(lib.open - _delay(lib.high, 1)) * _rank(lib.open - _delay(lib.close, 1)) * _rank(lib.open - _delay(lib.low, 1))


def _alpha108(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_signed_power(_rank(lib.high - _ts_min(lib.high, 2)), _rank(_corr(lib._vwap(), _ts_mean(lib.volume, 120), 6)))


def _alpha109(lib: GTJAAlpha191Library) -> pd.DataFrame:
    hl = lib.high - lib.low
    smooth = _sma(hl, 10, 2)
    return _safe_divide(smooth, _sma(smooth, 10, 2))


def _alpha110(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    return _safe_divide(_ts_sum(_elementwise_max(lib.high - previous, 0.0), 20), _ts_sum(_elementwise_max(previous - lib.low, 0.0), 20)) * 100.0


def _alpha111(lib: GTJAAlpha191Library) -> pd.DataFrame:
    value = _safe_divide(((lib.close - lib.low) - (lib.high - lib.close)) * lib.volume, lib.high - lib.low)
    return _sma(value, 11, 2) - _sma(value, 4, 2)


def _alpha112(lib: GTJAAlpha191Library) -> pd.DataFrame:
    change = lib.close - _delay(lib.close, 1)
    up = change.where(change > 0, 0.0)
    down = change.abs().where(change < 0, 0.0)
    up_sum = _ts_sum(up, 12)
    down_sum = _ts_sum(down, 12)
    return _safe_divide(up_sum - down_sum, up_sum + down_sum) * 100.0


def _alpha113(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_ts_sum(_delay(lib.close, 5), 20) / 20.0) * _corr(lib.close, lib.volume, 2) * _rank(_corr(_ts_sum(lib.close, 5), _ts_sum(lib.close, 20), 2))


def _alpha114(lib: GTJAAlpha191Library) -> pd.DataFrame:
    mean5 = _ts_mean(lib.close, 5)
    hl5 = _safe_divide(lib.high - lib.low, mean5)
    return _safe_divide(_rank(_delay(hl5, 2)) * _rank(_rank(lib.volume)), _safe_divide(hl5, lib._vwap() - lib.close))


def _alpha115(lib: GTJAAlpha191Library) -> pd.DataFrame:
    left = _rank(_corr(lib.high * 0.9 + lib.close * 0.1, _ts_mean(lib.volume, 30), 10))
    right = _rank(_corr(_ts_rank((lib.high + lib.low) / 2.0, 4), _ts_rank(lib.volume, 10), 7))
    return _signed_power(left, right)


def _alpha116(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _regbeta(lib.close, np.arange(1, 21, dtype=float), 20)


def _alpha117(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_rank(lib.volume, 32) * (1.0 - _ts_rank(lib.close + lib.high - lib.low, 16)) * (1.0 - _ts_rank(lib._returns(), 32))


def _alpha118(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(_ts_sum(lib.high - lib.open, 20), _ts_sum(lib.open - lib.low, 20)) * 100.0


def _alpha119(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(_decay_linear(_corr(lib._vwap(), _ts_sum(_ts_mean(lib.volume, 5), 26), 5), 7))
    second = _rank(_decay_linear(_ts_rank(_ts_min(_corr(_rank(lib.open), _rank(_ts_mean(lib.volume, 15)), 21), 9), 7), 8))
    return first - second


def _alpha120(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(_rank(lib._vwap() - lib.close), _rank(lib._vwap() + lib.close))


def _alpha121(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_signed_power(_rank(lib._vwap() - _ts_min(lib._vwap(), 12)), _ts_rank(_corr(_ts_rank(lib._vwap(), 20), _ts_rank(_ts_mean(lib.volume, 60), 2), 18), 3))


def _alpha122(lib: GTJAAlpha191Library) -> pd.DataFrame:
    triple = _sma(_sma(_sma(np.log(lib.close), 13, 2), 13, 2), 13, 2)
    return _safe_divide(triple - _delay(triple, 1), _delay(triple, 1))


def _alpha123(lib: GTJAAlpha191Library) -> pd.DataFrame:
    left = _rank(_corr(_ts_sum((lib.high + lib.low) / 2.0, 20), _ts_sum(_ts_mean(lib.volume, 60), 20), 9))
    right = _rank(_corr(lib.low, lib.volume, 6))
    return pd.DataFrame(np.where(left < right, -1.0, 1.0), index=lib.close.index, columns=lib.close.columns)


def _alpha124(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(lib.close - lib._vwap(), _decay_linear(_rank(_ts_max(lib.close, 30)), 2))


def _alpha125(lib: GTJAAlpha191Library) -> pd.DataFrame:
    numerator = _rank(_decay_linear(_corr(lib._vwap(), _ts_mean(lib.volume, 80), 17), 20))
    denominator = _rank(_decay_linear(_delta(lib.close * 0.5 + lib._vwap() * 0.5, 3), 16))
    return _safe_divide(numerator, denominator)


def _alpha126(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return (lib.close + lib.high + lib.low) / 3.0


def _alpha127(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return (_safe_divide(100.0 * (lib.close - _ts_max(lib.close, 12)), _ts_max(lib.close, 12))).abs()


def _alpha128(lib: GTJAAlpha191Library) -> pd.DataFrame:
    typical = (lib.high + lib.low + lib.close) / 3.0
    up = (typical * lib.volume).where(typical > _delay(typical, 1), 0.0)
    down = (typical * lib.volume).where(typical <= _delay(typical, 1), 0.0)
    ratio = _safe_divide(_ts_sum(up, 14), _ts_sum(down, 14))
    return 100.0 - _safe_divide(100.0, 1.0 + ratio)


def _alpha129(lib: GTJAAlpha191Library) -> pd.DataFrame:
    change = lib.close - _delay(lib.close, 1)
    return _ts_sum(change.abs().where(change < 0, 0.0), 12)


def _alpha130(lib: GTJAAlpha191Library) -> pd.DataFrame:
    numerator = _rank(_decay_linear(_corr((lib.high + lib.low) / 2.0, _ts_mean(lib.volume, 40), 9), 10))
    denominator = _rank(_decay_linear(_corr(_rank(lib._vwap()), _rank(lib.volume), 7), 3))
    return _safe_divide(numerator, denominator)


def _alpha131(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _signed_power(_rank(_delta(lib._vwap(), 1)), _ts_rank(_corr(lib.close, _ts_mean(lib.volume, 50), 18), 18))


def _alpha132(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_mean(lib._amount(), 20)


def _alpha133(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return (20.0 - _highday(lib.high, 20)) / 20.0 * 100.0 - (20.0 - _lowday(lib.low, 20)) / 20.0 * 100.0


def _alpha134(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(lib.close - _delay(lib.close, 12), _delay(lib.close, 12)) * lib.volume


def _alpha135(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _sma(_delay(_safe_divide(lib.close, _delay(lib.close, 20)), 1), 20, 1)


def _alpha136(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_delta(lib._returns(), 3)) * _corr(lib.open, lib.volume, 10)


def _alpha137(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous_close = _delay(lib.close, 1)
    previous_open = _delay(lib.open, 1)
    a = (lib.high - previous_close).abs()
    b = (lib.low - previous_close).abs()
    c = (lib.high - _delay(lib.low, 1)).abs()
    d = (previous_close - previous_open).abs()
    condition_a = (a > b) & (a > c)
    condition_b = (b > c) & (b > a)
    denominator = pd.DataFrame(np.where(condition_a, a + b / 2.0 + d / 4.0, np.where(condition_b, b + a / 2.0 + d / 4.0, c + d / 4.0)), index=lib.close.index, columns=lib.close.columns)
    return _safe_divide(16.0 * (lib.close + (lib.close - lib.open) / 2.0 - previous_open) * _elementwise_max(a, b), denominator)


def _alpha138(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(_decay_linear(_delta(lib.low * 0.7 + lib._vwap() * 0.3, 3), 20))
    second = _ts_rank(_decay_linear(_ts_rank(_corr(_ts_rank(lib.low, 8), _ts_rank(_ts_mean(lib.volume, 60), 17), 5), 19), 16), 7)
    return -(first - second)


def _alpha139(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_corr(lib.open, lib.volume, 10)


def _alpha140(lib: GTJAAlpha191Library) -> pd.DataFrame:
    left = _rank(_decay_linear((_rank(lib.open) + _rank(lib.low)) - (_rank(lib.high) + _rank(lib.close)), 8))
    right = _ts_rank(_decay_linear(_corr(_ts_rank(lib.close, 8), _ts_rank(_ts_mean(lib.volume, 60), 20), 8), 7), 3)
    return _elementwise_min(left, right)


def _alpha141(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_corr(_rank(lib.high), _rank(_ts_mean(lib.volume, 15)), 9))


def _alpha142(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_rank(_ts_rank(lib.close, 10)) * _rank(_delta(_delta(lib.close, 1), 1)) * _rank(_ts_rank(_safe_divide(lib.volume, _ts_mean(lib.volume, 20)), 5))


def _alpha143(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    growth = _safe_divide(lib.close - previous, previous)
    return growth.where((lib.close > previous) & growth.notna(), 1.0).cumprod()


def _alpha144(lib: GTJAAlpha191Library) -> pd.DataFrame:
    down = lib.close < _delay(lib.close, 1)
    part = _safe_divide((lib.close / _delay(lib.close, 1) - 1.0).abs(), lib._amount())
    return _safe_divide(_sumif(part, 20, down), _count(down, 20))


def _alpha145(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(_ts_mean(lib.volume, 9) - _ts_mean(lib.volume, 26), _ts_mean(lib.volume, 12)) * 100.0


def _alpha146(lib: GTJAAlpha191Library) -> pd.DataFrame:
    returns = _safe_divide(lib.close - _delay(lib.close, 1), _delay(lib.close, 1))
    deviation = returns - _sma(returns, 61, 2)
    denominator = _sma(deviation ** 2, 61, 2)
    return _safe_divide(_ts_mean(deviation, 20) * deviation, denominator)


def _alpha147(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _regbeta(_ts_mean(lib.close, 12), np.arange(1, 13, dtype=float), 12)


def _alpha148(lib: GTJAAlpha191Library) -> pd.DataFrame:
    left = _rank(_corr(lib.open, _ts_sum(_ts_mean(lib.volume, 60), 9), 6))
    right = _rank(lib.open - _ts_min(lib.open, 14))
    return pd.DataFrame(np.where(left < right, -1.0, 1.0), index=lib.close.index, columns=lib.close.columns)


def _alpha149(lib: GTJAAlpha191Library) -> pd.DataFrame:
    benchmark_close, _ = lib._benchmark()
    benchmark_return = benchmark_close.pct_change()
    down_market = benchmark_close < benchmark_close.shift(1)
    stock_return = lib._returns().where(down_market, axis=0)
    market_return = benchmark_return.where(down_market)
    market_panel = pd.DataFrame(np.broadcast_to(market_return.to_numpy()[:, None], lib.close.shape), index=lib.close.index, columns=lib.close.columns)
    return _regbeta(stock_return, market_panel, 252)


def _alpha150(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return (lib.close + lib.high + lib.low) / 3.0 * lib.volume


def _alpha151(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _sma(lib.close - _delay(lib.close, 20), 20, 1)


def _alpha152(lib: GTJAAlpha191Library) -> pd.DataFrame:
    inner = _sma(_delay(_safe_divide(lib.close, _delay(lib.close, 9)), 1), 9, 1)
    delayed = _delay(inner, 1)
    return _sma(_ts_mean(delayed, 12) - _ts_mean(delayed, 26), 9, 1)


def _alpha153(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return (_ts_mean(lib.close, 3) + _ts_mean(lib.close, 6) + _ts_mean(lib.close, 12) + _ts_mean(lib.close, 24)) / 4.0


def _alpha154(lib: GTJAAlpha191Library) -> pd.DataFrame:
    condition = lib._vwap() - _ts_min(lib._vwap(), 16) < _corr(lib._vwap(), _ts_mean(lib.volume, 180), 18)
    return pd.DataFrame(np.where(condition, 1.0, -1.0), index=lib.close.index, columns=lib.close.columns)


def _alpha155(lib: GTJAAlpha191Library) -> pd.DataFrame:
    fast = _sma(lib.volume, 13, 2)
    slow = _sma(lib.volume, 27, 2)
    diff = fast - slow
    return diff - _sma(diff, 10, 2)


def _alpha156(lib: GTJAAlpha191Library) -> pd.DataFrame:
    base = lib.open * 0.15 + lib.low * 0.85
    first = _rank(_decay_linear(_delta(lib._vwap(), 5), 3))
    second = _rank(_decay_linear(_safe_divide(_delta(base, 2), base) - 1.0, 3))
    return -_elementwise_max(first, second)


def _alpha157(lib: GTJAAlpha191Library) -> pd.DataFrame:
    inner = -_rank(_delta(lib.close - 1.0, 5))
    nested = _rank(_rank(inner))
    nested = np.log(_ts_sum(_ts_min(nested, 2), 1))
    nested = _ts_min(_rank(_rank(nested)), 5)
    return nested + _ts_rank(_delay(-lib._returns(), 6), 5)


def _alpha158(lib: GTJAAlpha191Library) -> pd.DataFrame:
    smooth = _sma(lib.close, 15, 2)
    return _safe_divide((lib.high - smooth) - (lib.low - smooth), lib.close)


def _alpha159(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    tr = _elementwise_max(lib.high, previous) - _elementwise_min(lib.low, previous)
    first = _safe_divide(lib.close - _ts_sum(_elementwise_min(lib.low, previous), 6), _ts_sum(tr, 6)) * 12.0 * 24.0
    second = _safe_divide(lib.close - _ts_sum(_elementwise_min(lib.low, previous), 12), _ts_sum(tr, 12)) * 6.0 * 24.0
    third = _safe_divide(lib.close - _ts_sum(_elementwise_min(lib.low, previous), 24), _ts_sum(tr, 24)) * 6.0 * 24.0
    return (first + second + third) * 100.0 / (6.0 * 12.0 + 6.0 * 24.0 + 12.0 * 24.0)


def _alpha160(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _sma(_ts_std(lib.close, 20).where(lib.close <= _delay(lib.close, 1), 0.0), 20, 1)


def _alpha161(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    true_range = _elementwise_max(_elementwise_max(lib.high - lib.low, (previous - lib.high).abs()), (previous - lib.low).abs())
    return _ts_mean(true_range, 12)


def _alpha162(lib: GTJAAlpha191Library) -> pd.DataFrame:
    change = lib.close - _delay(lib.close, 1)
    rsi = _safe_divide(_sma(_elementwise_max(change, 0.0), 12, 1), _sma(change.abs(), 12, 1)) * 100.0
    return _safe_divide(rsi - _ts_min(rsi, 12), _ts_max(rsi, 12) - _ts_min(rsi, 12))


def _alpha163(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _rank(-lib._returns() * _ts_mean(lib.volume, 20) * lib._vwap() * (lib.high - lib.close))


def _alpha164(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    change = lib.close - previous
    safe_change = change.where(change.abs() >= 0.01, np.sign(change) * 0.01)
    inner = _safe_divide(1.0, safe_change).where(lib.close > previous, 1.0)
    return _sma(_safe_divide(inner - _ts_min(inner, 12), lib.high - lib.low) * 100.0, 13, 2)


def _alpha165(lib: GTJAAlpha191Library) -> pd.DataFrame:
    x = _ts_sum(lib.close - _ts_mean(lib.close, 48), 48)
    maximum = _row_max(x)
    minimum = _row_min(x)
    std = _ts_std(lib.close, 48)
    return -_safe_divide(x.sub(maximum, axis=0), std).add(minimum, axis=0)


def _alpha166(lib: GTJAAlpha191Library) -> pd.DataFrame:
    returns = _safe_divide(lib.close, _delay(lib.close, 1)) - 1.0
    p1 = -20.0 * (20.0 - 1.0) ** 1.5 * _ts_sum(returns - _ts_mean(returns, 20), 20)
    p2 = (20.0 - 1.0) * (20.0 - 2.0) * _ts_sum((_ts_mean(_safe_divide(lib.close, _delay(lib.close, 1)), 20)) ** 2, 20) ** 1.5
    return _safe_divide(p1, p2)


def _alpha167(lib: GTJAAlpha191Library) -> pd.DataFrame:
    change = (lib.close - _delay(lib.close, 1)).where(lib.close > _delay(lib.close, 1), 0.0)
    return _ts_sum(change, 12)


def _alpha168(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_safe_divide(lib.volume, _ts_mean(lib.volume, 20))


def _alpha169(lib: GTJAAlpha191Library) -> pd.DataFrame:
    inner = _sma(lib.close - _delay(lib.close, 1), 9, 1)
    delayed = _delay(inner, 1)
    return _sma(_ts_mean(delayed, 12) - _ts_mean(delayed, 26), 10, 1)


def _alpha170(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _rank(_safe_divide(1.0, lib.close)) * _safe_divide(lib.volume, _ts_mean(lib.volume, 20))
    second = _safe_divide(lib.high * _rank(lib.high - lib.close), _ts_sum(lib.high, 5) / 5.0)
    return first * second - _rank(lib._vwap() - _delay(lib._vwap(), 5))


def _alpha171(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return -_safe_divide((lib.low - lib.close) * lib.open ** 5, (lib.close - lib.high) * lib.close ** 5)


def _directional_movement(lib: GTJAAlpha191Library) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    previous_close = _delay(lib.close, 1)
    true_range = _elementwise_max(_elementwise_max(lib.high - lib.low, (lib.high - previous_close).abs()), (lib.low - previous_close).abs())
    high_delta = lib.high - _delay(lib.high, 1)
    low_delta = _delay(lib.low, 1) - lib.low
    dm_plus = high_delta.where((high_delta > 0) & (high_delta > low_delta), 0.0)
    dm_minus = low_delta.where((low_delta > 0) & (low_delta > high_delta), 0.0)
    return true_range, dm_plus, dm_minus


def _alpha172(lib: GTJAAlpha191Library) -> pd.DataFrame:
    true_range, dm_plus, dm_minus = _directional_movement(lib)
    scale = _ts_sum(true_range, 14)
    plus = _safe_divide(_ts_sum(dm_plus, 14) * 100.0, scale)
    minus = _safe_divide(_ts_sum(dm_minus, 14) * 100.0, scale)
    return _ts_mean(_safe_divide((minus - plus).abs(), plus + minus) * 100.0, 6)


def _alpha173(lib: GTJAAlpha191Library) -> pd.DataFrame:
    first = _sma(lib.close, 13, 2)
    second = _sma(first, 13, 2)
    third = _sma(_sma(_sma(np.log(lib.close), 13, 2), 13, 2), 13, 2)
    return 3.0 * first - 2.0 * second + third


def _alpha174(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _sma(_ts_std(lib.close, 20).where(lib.close >= _delay(lib.close, 1), 0.0), 20, 1)


def _alpha175(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous = _delay(lib.close, 1)
    true_range = _elementwise_max(_elementwise_max(lib.high - lib.low, (previous - lib.high).abs()), (previous - lib.low).abs())
    return _ts_mean(true_range, 6)


def _alpha176(lib: GTJAAlpha191Library) -> pd.DataFrame:
    spread = _ts_max(lib.high, 12) - _ts_min(lib.low, 12)
    return _corr(_rank(_safe_divide(lib.close - _ts_min(lib.low, 12), spread)), _rank(lib.volume), 6)


def _alpha177(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return (20.0 - _highday(lib.high, 20)) / 20.0 * 100.0


def _alpha178(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _safe_divide(lib.close - _delay(lib.close, 1), _delay(lib.close, 1)) * lib.volume


def _alpha179(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _rank(_corr(lib._vwap(), lib.volume, 4)) * _rank(_corr(_rank(lib.low), _rank(_ts_mean(lib.volume, 50)), 12))


def _alpha180(lib: GTJAAlpha191Library) -> pd.DataFrame:
    change = _delta(lib.close, 7)
    signal = -_ts_rank(change.abs(), 60) * np.sign(change)
    return signal.where(_ts_mean(lib.volume, 20) < lib.volume, -lib.volume)


def _alpha181(lib: GTJAAlpha191Library) -> pd.DataFrame:
    benchmark_close, _ = lib._benchmark()
    returns = lib._returns()
    benchmark_deviation = benchmark_close - benchmark_close.rolling(20, min_periods=20).mean()
    deviation_panel = _broadcast_series(benchmark_deviation, lib.close)
    numerator = _ts_sum(returns - _ts_mean(returns, 20) - deviation_panel.pow(2), 20)
    denominator = _ts_sum(deviation_panel.abs().pow(3), 20)
    return _safe_divide(numerator, denominator)


def _alpha182(lib: GTJAAlpha191Library) -> pd.DataFrame:
    benchmark_close, benchmark_open = lib._benchmark()
    same_direction = ((lib.close > lib.open) & (benchmark_close > benchmark_open).to_numpy()[:, None]) | ((lib.close < lib.open) & (benchmark_close < benchmark_open).to_numpy()[:, None])
    return _count(same_direction, 20) / 20.0


def _alpha183(lib: GTJAAlpha191Library) -> pd.DataFrame:
    x = _ts_sum(lib.close - _ts_mean(lib.close, 24), 24)
    return -_safe_divide(x.sub(_row_max(x), axis=0), _ts_std(lib.close, 24)).add(_row_min(x), axis=0)


def _alpha184(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _rank(_corr(_delay(lib.open - lib.close, 1), lib.close, 200)) + _rank(lib.open - lib.close)


def _alpha185(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _rank(-((1.0 - _safe_divide(lib.open, lib.close)) ** 2))


def _alpha186(lib: GTJAAlpha191Library) -> pd.DataFrame:
    true_range, dm_plus, dm_minus = _directional_movement(lib)
    scale = _ts_sum(true_range, 14)
    plus = _safe_divide(_ts_sum(dm_plus, 14) * 100.0, scale)
    minus = _safe_divide(_ts_sum(dm_minus, 14) * 100.0, scale)
    adx = _ts_mean(_safe_divide((minus - plus).abs(), plus + minus) * 100.0, 6)
    return (adx + _delay(adx, 6)) / 2.0


def _alpha187(lib: GTJAAlpha191Library) -> pd.DataFrame:
    previous_open = _delay(lib.open, 1)
    return _ts_sum(_elementwise_max(lib.high - lib.open, lib.open - previous_open).where(lib.open > previous_open, 0.0), 20)


def _alpha188(lib: GTJAAlpha191Library) -> pd.DataFrame:
    hl = lib.high - lib.low
    smooth = _sma(hl, 11, 2)
    return _safe_divide(hl - smooth, smooth) * 100.0


def _alpha189(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _ts_mean((lib.close - _ts_mean(lib.close, 6)).abs(), 6)


def _alpha190(lib: GTJAAlpha191Library) -> pd.DataFrame:
    returns = _safe_divide(lib.close, _delay(lib.close, 1)) - 1.0
    threshold = _safe_divide(lib.close, _delay(lib.close, 19)) ** (1.0 / 20.0) - 1.0
    squared_error = (returns - threshold) ** 2
    up = returns > threshold
    down = returns < threshold
    numerator = (_count(up, 20) - 1.0) * _sumif(squared_error, 20, down)
    denominator = _count(down, 20) * _sumif(squared_error, 20, up)
    ratio = _safe_divide(numerator, denominator).where(lambda frame: frame > 0)
    return np.log(ratio)


def _alpha191(lib: GTJAAlpha191Library) -> pd.DataFrame:
    return _corr(_ts_mean(lib.volume, 20), lib.low, 5) + (lib.high + lib.low) / 2.0 - lib.close


_ALPHA_CALCULATORS: dict[int, Callable[[GTJAAlpha191Library], pd.DataFrame | None]] = {
    number: globals()[f"_alpha{number:03d}"] for number in range(1, 192)
}


def _add_alpha_method(number: int, calculator: Callable[[GTJAAlpha191Library], pd.DataFrame | None]) -> None:
    name = f"alpha191_{number:03d}"

    def factor(self: GTJAAlpha191Library, _calculator=calculator):
        return _align_result(_calculator(self), self.close)

    factor.__name__ = name
    factor.__doc__ = f"国泰君安 Alpha191 #{number:03d}。"
    setattr(GTJAAlpha191Library, name, factor)


for _number, _calculator in _ALPHA_CALCULATORS.items():
    _add_alpha_method(_number, _calculator)


__all__ = ["GTJAAlpha191Library"]
