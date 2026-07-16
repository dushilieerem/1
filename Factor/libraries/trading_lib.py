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
