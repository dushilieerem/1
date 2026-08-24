"""截面动量策略：持有过去 20 日收益最高的十只股票。"""

from app.quantcore import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)


class CrossSectionalMomentumStrategy(FactorPortfolioStrategy):
    """每个交易日按 20 日动量排名并等权配置 Top10。"""

    selector = TopN(10)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(1)

    @factor
    def momentum_20d(self):
        """过去 20 个交易日收益率。"""
        return self.close.pct_change(20)

    @signal
    def score(self):
        return self.momentum_20d()
