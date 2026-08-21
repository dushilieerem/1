"""波动率因子库。

风险/波动类因子，衡量价格的不确定性和尾部风险。
"""

from __future__ import annotations

import numpy as np

from app.quantcore import FactorLibrary


class VolatilityLib(FactorLibrary):
    """波动率因子集合。"""

    author = "SVQuant"

    # ==================== 历史波动率 ====================

    def volatility_5d(self, window: int = 5):
        """5 日波动率。"""
        return self.close.pct_change().rolling(window).std()

    def volatility_20d(self, window: int = 20):
        """20 日波动率。"""
        return self.close.pct_change().rolling(window).std()

    def volatility_60d(self, window: int = 60):
        """60 日波动率。"""
        return self.close.pct_change().rolling(window).std()

    def volatility_120d(self, window: int = 120):
        """120 日波动率。"""
        return self.close.pct_change().rolling(window).std()

    def volatility_250d(self, window: int = 250):
        """250 日波动率（年化）。"""
        return self.close.pct_change().rolling(window).std()

    # ==================== 波动率特征 ====================

    def volatility_ratio(self, short: int = 5, long: int = 20):
        """波动率比：短期波动 / 长期波动。"""
        short_vol = self.close.pct_change().rolling(short).std()
        long_vol = self.close.pct_change().rolling(long).std()
        return short_vol / (long_vol + 1e-10)

    def volatility_stability(self, window: int = 60):
        """波动率稳定性：波动率的负波动率。"""
        vol = self.close.pct_change().rolling(20).std()
        return -vol.pct_change().rolling(window).std()

    def cvar_5(self, window: int = 20):
        """CVaR 5%：条件风险价值（最差 5% 收益的均值）。"""
        ret = self.close.pct_change()
        return ret.rolling(window).apply(
            lambda x: x[x < x.quantile(0.05)].mean(), raw=True
        )

    def max_drawdown_20d(self, window: int = 20):
        """20 日最大回撤。"""
        rolling_max = self.close.rolling(window).max()
        return (self.close - rolling_max) / rolling_max

    def downside_vol(self, window: int = 20):
        """下行波动率：只考虑负收益的波动率。"""
        ret = self.close.pct_change()
        neg_ret = ret[ret < 0]
        return neg_ret.rolling(window).std()

    # ==================== 特异波动率 ====================

    def idiosyncratic_vol_20d(self, window: int = 20):
        """特异波动率：残差波动率（简化版）。"""
        ret = self.close.pct_change()
        mkt_ret = ret.mean(axis=1)
        residual = ret.sub(mkt_ret, axis=0)
        return residual.rolling(window).std()

    # ==================== 振幅 ====================

    def price_range(self, window: int = 5):
        """价格区间：（最高 - 最低）/ 收盘价。"""
        return (self.high.rolling(window).max() - self.low.rolling(window).min()) / self.close

    def high_low_ratio(self, window: int = 5):
        """高低比：（最高 - 最低）/ 均价。"""
        avg = (self.high + self.low) / 2
        return (self.high - self.low) / (avg + 1e-10)

    def intraday_volatility(self):
        """日内振幅：（最高 - 最低）/ 开盘价。"""
        return (self.high - self.low) / self.open

    def parkinson_volatility(self, window: int = 20):
        """Parkinson 波动率：基于高低价区间的波动率估计。"""
        variance = np.log(self.high / self.low).pow(2).rolling(window).mean() / (4 * np.log(2))
        return np.sqrt(variance)

    def garman_klass_volatility(self, window: int = 20):
        """Garman-Klass 波动率：基于开高低收价格的波动率估计。"""
        high_low = np.log(self.high / self.low)
        close_open = np.log(self.close / self.open)
        variance = (
            0.5 * high_low.pow(2) - (2 * np.log(2) - 1) * close_open.pow(2)
        ).rolling(window).mean()
        return np.sqrt(variance.clip(lower=0))

    def rogers_satchell_volatility(self, window: int = 20):
        """Rogers-Satchell 波动率：允许价格存在趋势漂移的 OHLC 估计。"""
        variance = (
            np.log(self.high / self.close) * np.log(self.high / self.open)
            + np.log(self.low / self.close) * np.log(self.low / self.open)
        ).rolling(window).mean()
        return np.sqrt(variance.clip(lower=0))

    def chaikin_volatility(self, ema_window: int = 10, change_window: int = 10):
        """Chaikin 波动率：高低价振幅 EMA 的变动百分比。"""
        high_low_average = (self.high - self.low).ewm(span=ema_window, adjust=False).mean()
        return (high_low_average / high_low_average.shift(change_window) - 1) * 100

    def gap(self):
        """跳空：（开盘价 - 前收盘价）/ 前收盘价。"""
        return self.open / self.pre_close - 1

    # ==================== 波动结构与尾部风险 ====================

    def atr_percent(self, window: int = 14):
        """归一化平均真实波幅：ATR / 收盘价绝对值。"""
        window = self._validate_window(window)
        true_range = self._true_range()
        atr = true_range.rolling(window).mean()
        price = self.close.abs()
        return atr / price.where(price > 1e-10)

    def atr_percentile(self, window: int = 14, rank_window: int = 60):
        """ATR 波动状态分位：当前归一化 ATR 在历史窗口中的百分位。"""
        window = self._validate_window(window)
        rank_window = self._validate_window(rank_window)
        atr = self.atr_percent(window=window)
        return atr.rolling(rank_window).apply(
            self._last_percentile_rank,
            raw=True,
        )

    def intraday_to_close_vol_ratio(self, window: int = 20):
        """日内区间波动与收盘收益波动之比。"""
        window = self._validate_window(window)
        high = self.high.where(self.high > 1e-10)
        low = self.low.where(self.low > 1e-10)
        range_log_return = np.log(high / low).replace([np.inf, -np.inf], np.nan)
        range_volatility = np.sqrt(
            range_log_return.pow(2).rolling(window).mean().clip(lower=0.0)
        )

        close = self.close.where(self.close > 1e-10)
        close_log_return = np.log(close / close.shift()).replace(
            [np.inf, -np.inf], np.nan
        )
        close_volatility = close_log_return.rolling(window).std(ddof=0)
        return range_volatility / close_volatility.where(
            close_volatility > 1e-10
        )

    def tail_loss_concentration(
        self, window: int = 20, tail_fraction: float = 0.2
    ):
        """尾部亏损集中度：最差若干负收益占窗口总亏损的比例。"""
        window = self._validate_window(window)
        tail_fraction = self._validate_tail_fraction(tail_fraction)
        returns = self.close.pct_change(fill_method=None).replace(
            [np.inf, -np.inf], np.nan
        )
        return returns.rolling(window).apply(
            lambda values: self._tail_loss_concentration(values, tail_fraction),
            raw=True,
        )

    @staticmethod
    def _last_percentile_rank(values: np.ndarray) -> float:
        if values.size == 0 or not np.isfinite(values).all():
            return np.nan
        current = values[-1]
        less = np.count_nonzero(values < current)
        equal = np.count_nonzero(values == current)
        return float((less + 0.5 * equal) / values.size)

    @staticmethod
    def _tail_loss_concentration(
        values: np.ndarray, tail_fraction: float
    ) -> float:
        if values.size == 0 or not np.isfinite(values).all():
            return np.nan
        losses = -values[values < 0.0]
        total_loss = losses.sum()
        if total_loss <= 1e-10:
            return 0.0
        tail_count = max(1, int(np.ceil(losses.size * tail_fraction)))
        tail_loss = np.sort(losses)[-tail_count:].sum()
        return float(tail_loss / total_loss)

    @staticmethod
    def _validate_window(window: int, minimum: int = 2) -> int:
        if isinstance(window, bool) or not isinstance(window, (int, np.integer)):
            raise ValueError(f"window 必须是大于等于 {minimum} 的整数")
        window = int(window)
        if window < minimum:
            raise ValueError(f"window 必须是大于等于 {minimum} 的整数")
        return window

    @staticmethod
    def _validate_tail_fraction(tail_fraction: float) -> float:
        if isinstance(tail_fraction, bool) or not isinstance(
            tail_fraction, (int, float, np.integer, np.floating)
        ):
            raise ValueError("tail_fraction 必须是大于 0 且不超过 1 的数")
        tail_fraction = float(tail_fraction)
        if not np.isfinite(tail_fraction) or not 0.0 < tail_fraction <= 1.0:
            raise ValueError("tail_fraction 必须是大于 0 且不超过 1 的数")
        return tail_fraction

    def _true_range(self):
        previous_close = self.close.shift()
        first = self.high - self.low
        second = (self.high - previous_close).abs()
        third = (self.low - previous_close).abs()
        result = first.where(first >= second, second)
        return result.where(result >= third, third)
