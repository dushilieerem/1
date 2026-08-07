"""波动率因子库。

风险/波动类因子，衡量价格的不确定性和尾部风险。
"""

from __future__ import annotations

import numpy as np

from quantcore import FactorLibrary


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
