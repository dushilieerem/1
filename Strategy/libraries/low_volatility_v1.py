"""低波动策略：持有过去 20 日收益波动最低的十只股票。"""

import pandas as pd


class LowVolatilityStrategy:
    """以 20 日收益标准差为风险分数，等权配置低波动 Top10。"""

    def __init__(self, close: pd.DataFrame):
        self.close = close

    def generate_signals(self) -> pd.DataFrame:
        volatility = self.close.pct_change().rolling(20).std()
        selected = volatility.rank(axis=1, ascending=True, method="first").le(10) & volatility.notna()
        return selected.div(selected.sum(axis=1), axis=0).fillna(0.0)
