"""技术因子库。

技术分析类因子，基于价格形态和技术指标。
"""

from __future__ import annotations

import numpy as np

from quantcore import FactorLibrary


class TechnicalLib(FactorLibrary):
    """技术因子集合。"""

    author = "SVQuant"

    # ==================== 均线 ====================

    def sma_5(self, window: int = 5):
        """5 日均线乖离率：（收盘价 - 均线）/ 均线。"""
        ma = self.close.rolling(window).mean()
        return (self.close - ma) / ma

    def sma_20(self, window: int = 20):
        """20 日均线乖离率。"""
        ma = self.close.rolling(window).mean()
        return (self.close - ma) / ma

    def sma_60(self, window: int = 60):
        """60 日均线乖离率。"""
        ma = self.close.rolling(window).mean()
        return (self.close - ma) / ma

    def ma_cross(self, fast: int = 5, slow: int = 20):
        """均线交叉：短期均线 / 长期均线 - 1。"""
        ma_fast = self.close.rolling(fast).mean()
        ma_slow = self.close.rolling(slow).mean()
        return ma_fast / ma_slow - 1

    def ma_distance(self, fast: int = 5, slow: int = 20):
        """均线距离：(短期 - 长期) / 长期。"""
        ma_fast = self.close.rolling(fast).mean()
        ma_slow = self.close.rolling(slow).mean()
        return (ma_fast - ma_slow) / ma_slow

    # ==================== RSI ====================

    def rsi_6(self, window: int = 6):
        """6 日 RSI。"""
        delta = self.close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = -delta.clip(upper=0).rolling(window).mean()
        rs = gain / (loss + 1e-10)
        return 100 - 100 / (1 + rs)

    def rsi_14(self, window: int = 14):
        """14 日 RSI。"""
        delta = self.close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = -delta.clip(upper=0).rolling(window).mean()
        rs = gain / (loss + 1e-10)
        return 100 - 100 / (1 + rs)

    def rsi_24(self, window: int = 24):
        """24 日 RSI。"""
        delta = self.close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = -delta.clip(upper=0).rolling(window).mean()
        rs = gain / (loss + 1e-10)
        return 100 - 100 / (1 + rs)

    # ==================== MACD ====================

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD 因子。"""
        ema_fast = self.close.ewm(span=fast).mean()
        ema_slow = self.close.ewm(span=slow).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal).mean()
        return dif - dea

    def macd_signal(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD 信号线：DIF - DEA 的归一化。"""
        ema_fast = self.close.ewm(span=fast).mean()
        ema_slow = self.close.ewm(span=slow).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal).mean()
        return (dif - dea) / (dif.abs().mean() + 1e-10)

    def macd_cross(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD 金叉死叉信号。"""
        ema_fast = self.close.ewm(span=fast).mean()
        ema_slow = self.close.ewm(span=slow).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal).mean()
        hist = dif - dea
        cross = hist.rolling(2).apply(lambda x: x.iloc[-1] - x.iloc[0], raw=True)
        return cross

    # ==================== 布林带 ====================

    def bollinger_position(self, window: int = 20, n_std: float = 2.0):
        """布林带位置：（收盘价 - 下轨）/（上轨 - 下轨）。"""
        mid = self.close.rolling(window).mean()
        std = self.close.rolling(window).std()
        upper = mid + n_std * std
        lower = mid - n_std * std
        return (self.close - lower) / (upper - lower + 1e-10)

    def bollinger_width(self, window: int = 20, n_std: float = 2.0):
        """布林带宽度：（上轨 - 下轨）/ 中轨。"""
        mid = self.close.rolling(window).mean()
        std = self.close.rolling(window).std()
        return (2 * n_std * std) / mid

    def bollinger_breakout(self, window: int = 20, n_std: float = 2.0):
        """布林带突破：收盘价超出上轨为 1，低于下轨为 -1，否则 0。"""
        mid = self.close.rolling(window).mean()
        std = self.close.rolling(window).std()
        upper = mid + n_std * std
        lower = mid - n_std * std
        breakout = (self.close > upper).astype(float) - (self.close < lower).astype(float)
        return breakout

    # ==================== 随机指标 ====================

    def kdj_k(self, window: int = 9):
        """KDJ K 值。"""
        hh = self.high.rolling(window).max()
        ll = self.low.rolling(window).min()
        return (self.close - ll) / (hh - ll + 1e-10) * 100

    def kdj_d(self, window: int = 9, k_smooth: int = 3):
        """KDJ D 值。"""
        hh = self.high.rolling(window).max()
        ll = self.low.rolling(window).min()
        k = (self.close - ll) / (hh - ll + 1e-10) * 100
        return k.rolling(k_smooth).mean()

    def stoch_rsi(self, window: int = 14):
        """随机 RSI。"""
        rsi = self.rsi_14(window=window)
        hh = rsi.rolling(window).max()
        ll = rsi.rolling(window).min()
        return (rsi - ll) / (hh - ll + 1e-10)

    def cci(self, window: int = 20):
        """商品通道指数：典型价格偏离其平均值的程度。"""
        typical_price = (self.high + self.low + self.close) / 3
        mean = typical_price.rolling(window).mean()
        mean_deviation = typical_price.rolling(window).apply(
            lambda values: np.mean(np.abs(values - values.mean())), raw=True
        )
        return (typical_price - mean) / (0.015 * mean_deviation + 1e-10)

    def williams_r(self, window: int = 14):
        """Williams %R：收盘价在近期高低区间中的位置。"""
        highest_high = self.high.rolling(window).max()
        lowest_low = self.low.rolling(window).min()
        return -100 * (highest_high - self.close) / (highest_high - lowest_low + 1e-10)

    # ==================== 价格形态 ====================

    def price_pattern_doji(self):
        """十字星形态。"""
        body = (self.open - self.close).abs()
        shadow = self.high - self.low
        return (body / (shadow + 1e-10) < 0.1).astype(float)

    def price_pattern_hammer(self):
        """锤子线形态。"""
        body = (self.open - self.close).abs()
        lower_shadow = self.close - self.low
        upper_shadow = self.high - self.open
        return ((lower_shadow > body * 2) & (upper_shadow < body * 0.5)).astype(float)
