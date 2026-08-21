"""量价因子库。

成交量和量价关系类因子。
"""

from __future__ import annotations

import numpy as np

from app.quantcore import FactorLibrary


class TradingLib(FactorLibrary):
    """量价因子集合。"""

    author = "SVQuant"

    # ==================== 成交量 ====================

    def volume_5d(self, window: int = 5):
        """5 日均量：成交量 / 过去 window 日均量。"""
        return self.volume / self.volume.rolling(window).mean()

    def volume_20d(self, window: int = 20):
        """20 日均量。"""
        return self.volume / self.volume.rolling(window).mean()

    def volume_60d(self, window: int = 60):
        """60 日均量。"""
        return self.volume / self.volume.rolling(window).mean()

    def volume_std(self, window: int = 20):
        """成交量波动：成交量的 ZSCORE。"""
        vol = self.volume
        return (vol - vol.rolling(window).mean()) / vol.rolling(window).std()

    def volume_shock(self, window: int = 5):
        """成交量突变：当日量 / 前 window 日最小量。"""
        return self.volume / self.volume.rolling(window).min()

    # ==================== 金额 ====================

    def amount_5d(self, window: int = 5):
        """5 日成交额比。"""
        return self.amount / self.amount.rolling(window).mean()

    def amount_20d(self, window: int = 20):
        """20 日成交额比。"""
        return self.amount / self.amount.rolling(window).mean()

    # ==================== 换手率 ====================

    def turnover_5d(self, window: int = 5):
        """5 日平均换手率。"""
        return self.turnover.rolling(window).mean()

    def turnover_20d(self, window: int = 20):
        """20 日平均换手率。"""
        return self.turnover.rolling(window).mean()

    def turnover_std(self, window: int = 20):
        """换手率波动。"""
        return self.turnover.rolling(window).std()

    # ==================== 量价关系 ====================

    def volume_price_corr(self, window: int = 10):
        """量价相关性：成交量和价格的相关系数。"""
        ret = self.close.pct_change()
        vol = self.volume.pct_change()
        return ret.rolling(window).corr(vol)

    def volume_confirmation(self, window: int = 5):
        """量能确认：上涨时放量，下跌时缩量。"""
        ret = self.close.pct_change()
        vol_ratio = self.volume / self.volume.rolling(window).mean()
        return ret * vol_ratio

    def volume_price_trend(self, window: int = 20):
        """量价趋势：价格趋势 × 量能趋势。"""
        price_trend = self.close / self.close.rolling(window).mean() - 1
        vol_trend = self.volume / self.volume.rolling(window).mean() - 1
        return price_trend * vol_trend

    def volume_divergence(self, window: int = 10):
        """量价背离：价格创新高但量能没跟上。"""
        price_high = self.close == self.close.rolling(window).max()
        vol_avg = self.volume / self.volume.rolling(window).mean()
        return (price_high.astype(float) * (1 - vol_avg)) * (-1)

    # ==================== 资金流 ====================

    def money_flow(self, window: int = 5):
        """资金流：价格变动 × 成交量。"""
        ret = self.close.pct_change()
        return (ret * self.volume).rolling(window).sum()

    def net_buy_ratio(self, window: int = 5):
        """净买入比。"""
        ret = self.close.pct_change()
        buy_vol = ret.clip(lower=0) * self.volume
        sell_vol = (-ret).clip(lower=0) * self.volume
        buy_sum = buy_vol.rolling(window).sum()
        sell_sum = sell_vol.rolling(window).sum()
        return (buy_sum - sell_sum) / (buy_sum + sell_sum + 1e-10)

    def obv(self):
        """能量潮：按收盘涨跌累计成交量，起始值为 0。"""
        direction = (
            self.close.diff().gt(0).astype(float)
            - self.close.diff().lt(0).astype(float)
        )
        return (direction * self.volume).cumsum()

    def chaikin_money_flow(self, window: int = 21):
        """Chaikin 资金流：量价累积/派发在窗口内的成交量加权均值。"""
        multiplier = ((self.close - self.low) - (self.high - self.close)) / (
            self.high - self.low + 1e-10
        )
        return (
            (multiplier * self.volume).rolling(window).sum()
            / self.volume.rolling(window).sum()
        )

    def positive_volume_index(self, base_value: float = 1000.0):
        """正量指标：仅在成交量增加时累计收盘收益。"""
        factor = (1 + self.close.pct_change()).where(
            self.volume > self.volume.shift(), 1.0
        ).fillna(1.0)
        return base_value * factor.cumprod()

    def negative_volume_index(self, base_value: float = 1000.0):
        """负量指标：仅在成交量减少时累计收盘收益。"""
        factor = (1 + self.close.pct_change()).where(
            self.volume < self.volume.shift(), 1.0
        ).fillna(1.0)
        return base_value * factor.cumprod()

    def chaikin_oscillator(self, fast: int = 3, slow: int = 10):
        """Chaikin Oscillator：累积/派发线的快慢 EMA 差。"""
        multiplier = ((self.close - self.low) - (self.high - self.close)) / (
            self.high - self.low + 1e-10
        )
        accumulation_distribution = (multiplier * self.volume).cumsum()
        return (
            accumulation_distribution.ewm(span=fast, adjust=False).mean()
            - accumulation_distribution.ewm(span=slow, adjust=False).mean()
        )

    def volume_oscillator(self, short: int = 5, long: int = 20):
        """成交量振荡器：短期与长期平均成交量的百分比差。"""
        short_average = self.volume.rolling(short).mean()
        long_average = self.volume.rolling(long).mean()
        return (short_average / (long_average + 1e-10) - 1) * 100

    # ==================== 成交量结构与时序 ====================

    def up_down_volume_imbalance(self, window: int = 20):
        """涨跌成交量失衡：上涨日与下跌日成交量的净差占比。"""
        window = self._validate_window(window)
        returns = self.close.pct_change(fill_method=None).replace(
            [np.inf, -np.inf], np.nan
        )
        direction = (
            returns.gt(0).astype(float) - returns.lt(0).astype(float)
        ).where(returns.notna())
        volume = self._nonnegative_volume()
        signed_volume = direction * volume
        numerator = signed_volume.rolling(window).sum()
        denominator = volume.rolling(window).sum()
        result = numerator / (denominator + 1e-10)
        result = result.where(numerator.notna() & denominator.notna())
        return result.where(
            denominator.isna() | (denominator > 1e-10), 0.0
        ).clip(lower=-1.0, upper=1.0)

    def volume_concentration(
        self, window: int = 20, tail_fraction: float = 0.2
    ):
        """成交量集中度：窗口内最大成交量尾部占总成交量的比例。"""
        window = self._validate_window(window)
        tail_fraction = self._validate_tail_fraction(tail_fraction)
        volume = self._nonnegative_volume()
        return volume.rolling(window).apply(
            lambda values: self._top_tail_share(values, tail_fraction),
            raw=True,
        )

    def volume_autocorrelation(self, window: int = 20, lag: int = 1):
        """成交量自相关：对数成交量变化的滞后相关性。"""
        window = self._validate_window(window)
        lag = self._validate_lag(window, lag)
        changes = self._log_volume_change()
        return self._rolling_correlation(changes, changes.shift(lag), window)

    def volume_return_lead_lag(self, window: int = 20, lag: int = 1):
        """成交量领先收益相关：滞后成交量变化与当前收益的滚动相关性。"""
        window = self._validate_window(window)
        lag = self._validate_lag(window, lag)
        returns = self.close.pct_change(fill_method=None).replace(
            [np.inf, -np.inf], np.nan
        )
        changes = self._log_volume_change()
        return self._rolling_correlation(returns, changes.shift(lag), window)

    @staticmethod
    def _validate_window(window: int, minimum: int = 2) -> int:
        if isinstance(window, bool) or not isinstance(window, (int, np.integer)):
            raise ValueError(f"window 必须是大于等于 {minimum} 的整数")
        window = int(window)
        if window < minimum:
            raise ValueError(f"window 必须是大于等于 {minimum} 的整数")
        return window

    def _validate_lag(self, window: int, lag: int) -> int:
        lag = self._validate_window(lag, minimum=1)
        if lag >= window:
            raise ValueError("lag 必须小于 window")
        return lag

    @staticmethod
    def _validate_tail_fraction(tail_fraction: float) -> float:
        if isinstance(tail_fraction, bool) or not isinstance(
            tail_fraction, (int, float, np.integer, np.floating)
        ):
            raise ValueError("tail_fraction 必须是 (0, 1] 范围内的有限数值")
        tail_fraction = float(tail_fraction)
        if not np.isfinite(tail_fraction) or not 0.0 < tail_fraction <= 1.0:
            raise ValueError("tail_fraction 必须是 (0, 1] 范围内的有限数值")
        return tail_fraction

    def _nonnegative_volume(self):
        return self.volume.where(self.volume >= 0).replace(
            [np.inf, -np.inf], np.nan
        )

    def _log_volume_change(self):
        volume = self.volume.where(self.volume > 0).replace(
            [np.inf, -np.inf], np.nan
        )
        return np.log(volume).diff()

    @staticmethod
    def _top_tail_share(values: np.ndarray, tail_fraction: float) -> float:
        total = float(values.sum())
        if not np.isfinite(total) or total <= 1e-10:
            return 0.0
        tail_count = max(1, int(np.ceil(values.size * tail_fraction)))
        largest = np.partition(values, values.size - tail_count)[-tail_count:]
        return float(largest.sum() / total)

    @staticmethod
    def _rolling_correlation(left, right, window: int):
        left_mean = left.rolling(window).mean()
        right_mean = right.rolling(window).mean()
        covariance = (
            (left * right).rolling(window).mean() - left_mean * right_mean
        )
        left_variance = (
            left.pow(2).rolling(window).mean() - left_mean.pow(2)
        ).clip(lower=0.0)
        right_variance = (
            right.pow(2).rolling(window).mean() - right_mean.pow(2)
        ).clip(lower=0.0)
        denominator = np.sqrt(left_variance * right_variance)
        result = covariance / denominator.where(denominator > 1e-10)
        result = result.where(denominator.notna())
        return result.where(
            denominator.isna() | (denominator > 1e-10), 0.0
        ).clip(lower=-1.0, upper=1.0)
