"""聚宽兼容技术指标（第一批）。

本模块只实现已确认可由复权收盘价直接计算的指标。名称以 ``jq_``
前缀隔离，避免改变既有 SVQuant 因子语义。
"""

from __future__ import annotations

from quantcore import FactorLibrary


class JoinQuantTechnicalLibrary(FactorLibrary):
    """聚宽技术指标兼容因子。"""

    author = "SVQuant"

    def jq_boll_down(self, window: int = 20, n_std: float = 2.0):
        """聚宽 boll_down：20 日布林线下轨。"""
        middle = self.close.rolling(window).mean()
        return (middle - n_std * self.close.rolling(window).std()) / self.close

    def jq_boll_up(self, window: int = 20, n_std: float = 2.0):
        """聚宽 boll_up：20 日布林线上轨。"""
        middle = self.close.rolling(window).mean()
        return (middle + n_std * self.close.rolling(window).std()) / self.close

    def jq_ema5(self):
        """聚宽 EMA5：5 日指数移动均线。"""
        return self.close.ewm(span=5, adjust=False).mean() / self.close

    def jq_emac10(self):
        """聚宽 EMAC10：10 日收盘价指数移动均线。"""
        return self.close.ewm(span=10, adjust=False).mean() / self.close

    def jq_emac12(self):
        """聚宽 EMAC12：12 日收盘价指数移动均线。"""
        return self.close.ewm(span=12, adjust=False).mean() / self.close

    def jq_emac20(self):
        """聚宽 EMAC20：20 日收盘价指数移动均线。"""
        return self.close.ewm(span=20, adjust=False).mean() / self.close

    def jq_emac26(self):
        """聚宽 EMAC26：26 日收盘价指数移动均线。"""
        return self.close.ewm(span=26, adjust=False).mean() / self.close

    def jq_emac120(self):
        """聚宽 EMAC120：120 日收盘价指数移动均线。"""
        return self.close.ewm(span=120, adjust=False).mean() / self.close

    def jq_mac5(self):
        """聚宽 MAC5：5 日移动均线。"""
        return self.close.rolling(5).mean() / self.close

    def jq_mac10(self):
        """聚宽 MAC10：10 日移动均线。"""
        return self.close.rolling(10).mean() / self.close

    def jq_mac20(self):
        """聚宽 MAC20：20 日移动均线。"""
        return self.close.rolling(20).mean() / self.close

    def jq_mac60(self):
        """聚宽 MAC60：60 日移动均线。"""
        return self.close.rolling(60).mean() / self.close

    def jq_mac120(self):
        """聚宽 MAC120：120 日移动均线。"""
        return self.close.rolling(120).mean() / self.close

    def jq_macdc(self):
        """聚宽 MACDC：MACD 柱值除以当日收盘价。"""
        fast = self.close.ewm(span=12, adjust=False).mean()
        slow = self.close.ewm(span=26, adjust=False).mean()
        diff = fast - slow
        dea = diff.ewm(span=9, adjust=False).mean()
        return (diff - dea) / self.close

    def jq_mfi14(self):
        """聚宽 MFI14：14 日资金流量指标。"""
        typical_price = (self.high + self.low + self.close) / 3
        money_flow = typical_price * self.volume
        positive = money_flow.where(typical_price > typical_price.shift(), 0.0)
        negative = money_flow.where(typical_price < typical_price.shift(), 0.0)
        money_ratio = positive.rolling(14).sum() / negative.rolling(14).sum()
        return 100 - 100 / (1 + money_ratio)
