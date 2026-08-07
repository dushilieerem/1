"""量价因子库。

成交量和量价关系类因子。
"""

from __future__ import annotations

from quantcore import FactorLibrary


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
