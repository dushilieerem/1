"""低波动策略：持有过去 20 日收益波动最低的十只股票。"""

from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)


class LowVolatilityStrategy(FactorPortfolioStrategy):
    """以 20 日收益标准差为风险分数，等权配置低波动 Top10。"""

    selector = TopN(10)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(1)

    @factor
    def negative_volatility_20d(self):
        """过去 20 日收益波动率的相反数，波动越低分数越高。"""
        return -self.close.pct_change().rolling(20).std()

    @signal
    def score(self):
        return self.negative_volatility_20d()
