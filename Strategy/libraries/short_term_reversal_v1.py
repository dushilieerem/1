"""短期反转策略：持有过去 5 日收益最低的十只股票。"""

from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)


class ShortTermReversalStrategy(FactorPortfolioStrategy):
    """每个交易日按短期收益从低到高排名并等权配置 Top10。"""

    selector = TopN(10)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(1)

    @factor
    def reversal_5d(self):
        """过去 5 个交易日收益率的相反数，跌幅越大分数越高。"""
        return -self.close.pct_change(5)

    @signal
    def score(self):
        return self.reversal_5d()
