"""双均线趋势策略：快均线高于慢均线时等权持有。"""

from quantcore import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)


class DualMovingAverageStrategy(FactorPortfolioStrategy):
    """使用 20/60 日均线识别趋势，只依赖收盘价。"""

    selector = TopN(5000)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(1)

    @factor
    def moving_average_spread(self):
        """20 日均线与 60 日均线之差。"""
        return self.close.rolling(20).mean() - self.close.rolling(60).mean()

    @signal
    def score(self):
        spread = self.moving_average_spread()
        return spread.where(spread > 0)
