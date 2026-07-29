"""唐奇安突破策略：仅持有创 60 日新高的股票。"""

from quantcore import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)


class DonchianBreakoutStrategy(FactorPortfolioStrategy):
    """以收盘价突破过去 60 日高点作为趋势入场信号。"""

    selector = TopN(5000)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(1)

    @factor
    def breakout_score_60d(self):
        """仅对创 60 日新高的标的返回收盘价分数。"""
        channel_high = self.close.rolling(60, min_periods=60).max()
        return self.close.where(self.close.ge(channel_high) & channel_high.notna())

    @signal
    def score(self):
        return self.breakout_score_60d()
