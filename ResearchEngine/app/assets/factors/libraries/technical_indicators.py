"""技术指标（第一批）。"""

from __future__ import annotations

from app.quantcore import FactorLibrary


class TechnicalIndicatorLibrary(FactorLibrary):
    """技术指标因子。"""

    author = "SVQuant"

    def boll_down(self, window: int = 20, n_std: float = 2.0):
        """20 日布林线下轨。"""
        middle = self.close.rolling(window).mean()
        return (middle - n_std * self.close.rolling(window).std()) / self.close

    def boll_up(self, window: int = 20, n_std: float = 2.0):
        """20 日布林线上轨。"""
        middle = self.close.rolling(window).mean()
        return (middle + n_std * self.close.rolling(window).std()) / self.close

    def ema5(self):
        """5 日指数移动均线。"""
        return self.close.ewm(span=5, adjust=False).mean() / self.close

    def emac10(self):
        """聚宽 EMAC10：10 日收盘价指数移动均线。"""
        return self.close.ewm(span=10, adjust=False).mean() / self.close

    def emac12(self):
        """聚宽 EMAC12：12 日收盘价指数移动均线。"""
        return self.close.ewm(span=12, adjust=False).mean() / self.close

    def emac20(self):
        """聚宽 EMAC20：20 日收盘价指数移动均线。"""
        return self.close.ewm(span=20, adjust=False).mean() / self.close

    def emac26(self):
        """聚宽 EMAC26：26 日收盘价指数移动均线。"""
        return self.close.ewm(span=26, adjust=False).mean() / self.close

    def emac120(self):
        """聚宽 EMAC120：120 日收盘价指数移动均线。"""
        return self.close.ewm(span=120, adjust=False).mean() / self.close

    def mac5(self):
        """聚宽 MAC5：5 日移动均线。"""
        return self.close.rolling(5).mean() / self.close

    def mac10(self):
        """聚宽 MAC10：10 日移动均线。"""
        return self.close.rolling(10).mean() / self.close

    def mac20(self):
        """聚宽 MAC20：20 日移动均线。"""
        return self.close.rolling(20).mean() / self.close

    def mac60(self):
        """聚宽 MAC60：60 日移动均线。"""
        return self.close.rolling(60).mean() / self.close

    def mac120(self):
        """聚宽 MAC120：120 日移动均线。"""
        return self.close.rolling(120).mean() / self.close

    def macdc(self):
        """聚宽 MACDC：MACD 柱值除以当日收盘价。"""
        fast = self.close.ewm(span=12, adjust=False).mean()
        slow = self.close.ewm(span=26, adjust=False).mean()
        diff = fast - slow
        dea = diff.ewm(span=9, adjust=False).mean()
        return (diff - dea) / self.close

    def mfi14(self):
        """聚宽 MFI14：14 日资金流量指标。"""
        typical_price = (self.high + self.low + self.close) / 3
        money_flow = typical_price * self.volume
        positive = money_flow.where(typical_price > typical_price.shift(), 0.0)
        negative = money_flow.where(typical_price < typical_price.shift(), 0.0)
        money_ratio = positive.rolling(14).sum() / negative.rolling(14).sum()
        return 100 - 100 / (1 + money_ratio)
