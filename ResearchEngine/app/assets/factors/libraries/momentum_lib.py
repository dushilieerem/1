"""动量因子库。

动量/趋势类因子，衡量价格变化的速度与方向。
"""

from __future__ import annotations

from app.quantcore import FactorLibrary


class MomentumLib(FactorLibrary):
    """动量因子集合。"""

    author = "SVQuant"

    # ==================== 简单动量 ====================

    def momentum_5d(self, window: int = 5):
        """5 日动量：过去 window 日收益率。"""
        return self.close.pct_change(window)

    def momentum_10d(self, window: int = 10):
        """10 日动量。"""
        return self.close.pct_change(window)

    def momentum_20d(self, window: int = 20):
        """20 日动量（约月）。"""
        return self.close.pct_change(window)

    def momentum_60d(self, window: int = 60):
        """60 日动量（约季）。"""
        return self.close.pct_change(window)

    def momentum_120d(self, window: int = 120):
        """120 日动量（约半年）。"""
        return self.close.pct_change(window)

    def momentum_250d(self, window: int = 250):
        """250 日动量（约年）。"""
        return self.close.pct_change(window)

    # ==================== 复合动量 ====================

    def momentum_ratio(self, short: int = 5, long: int = 20):
        """动量比：短期动量 / 长期动量。"""
        short_ret = self.close.pct_change(short)
        long_ret = self.close.pct_change(long).abs()
        return short_ret / (long_ret + 1e-10)

    def momentum_acceleration(self, fast: int = 5, slow: int = 20):
        """动量加速度：短期动量 - 长期动量。"""
        return self.close.pct_change(fast) - self.close.pct_change(slow)

    def momentum_decay(self, window: int = 20, decay: float = 0.9):
        """指数衰减动量：对每日收益率加权平均，越近权重越高。"""
        ret = self.close.pct_change()
        weights = [decay ** i for i in range(window)]
        weights = weights[::-1]  # 最近权重最大
        weights = [w / sum(weights) for w in weights]
        return ret.rolling(window).apply(lambda x: (x * weights).sum(), raw=True)

    def momentum_risk_adjusted(self, window: int = 20):
        """风险调整动量：收益率 / 波动率。"""
        ret = self.close.pct_change(window)
        vol = self.close.pct_change().rolling(window).std()
        return ret / (vol + 1e-10)

    # ==================== 反转因子 ====================

    def reversal_1d(self):
        """1 日反转。"""
        return -self.close.pct_change(1)

    def reversal_5d(self, window: int = 5):
        """5 日反转。"""
        return -self.close.pct_change(window)

    def reversal_20d(self, window: int = 20):
        """20 日反转。"""
        return -self.close.pct_change(window)

    def reversal_60d(self, window: int = 60):
        """60 日反转。"""
        return -self.close.pct_change(window)

    def reversal_industry_neutral(self, window: int = 20):
        """行业中性反转：减去行业均值。"""
        raw = -self.close.pct_change(window)
        # 行业中性化由系统处理，此处直接返回原始值
        return raw

    # ==================== 趋势强度 ====================

    def trend_strength(self, window: int = 20):
        """趋势强度：当前价 / 均价。"""
        return self.close / self.close.rolling(window).mean()

    def trend_position(self, window: int = 60):
        """趋势位置：（当前价 - 最低价）/（最高价 - 最低价）。"""
        hh = self.high.rolling(window).max()
        ll = self.low.rolling(window).min()
        return (self.close - ll) / (hh - ll + 1e-10)

    def trend_consistency(self, window: int = 10):
        """趋势一致性：上涨天数占比。"""
        up = (self.close.diff() > 0).astype(float)
        return up.rolling(window).mean()
