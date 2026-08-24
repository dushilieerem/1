"""Alpha 因子库（面板模式 + FactorLibrary）。

研究员直接写方法，不用写类、name、compute 这些样板。
库的 author 对所有因子生效。

方法内 ``self.close`` 就是 ``日期×标的`` 收盘价宽表，直接向量化算。
"""

from __future__ import annotations

from app.quantcore import FactorLibrary


class AlphaLibrary(FactorLibrary):
    """Alpha 101 / 158 经典因子集合。"""

    author = "SVQuant"

    def alpha101(self, window: int = 5):
        """动量因子：过去 ``window`` 日收益率。"""
        return self.close.pct_change(window)

    def alpha158(self, window: int = 5):
        """反转因子：-过去 ``window`` 日收益率。"""
        return -self.close.pct_change(window)

    def marketcap(self):
        return -self.total_mv

    def macdboll(self):
        ema12 = self.close.ewm(span=12).mean()
        ema26 = self.close.ewm(span=26).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9).mean()
        macd = dif - dea

        mid = self.close.rolling(20).mean()
        std = self.close.rolling(20).std()

        upper = mid + 2 * std
        lower = mid - 2 * std

        boll_pos = (self.close - lower) / (upper - lower)

        return macd * (1 - boll_pos)

    def futureRes(self):
        return self.close.shift(-1) - self.close