"""短期反转策略：持有过去 5 日收益最低的十只股票。"""

import pandas as pd


class ShortTermReversalStrategy:
    """每个交易日按短期收益从低到高排名并等权配置 Top10。"""

    def __init__(self, close: pd.DataFrame):
        self.close = close

    def generate_signals(self) -> pd.DataFrame:
        score = self.close.pct_change(5)
        selected = score.rank(axis=1, ascending=True, method="first").le(10) & score.notna()
        return selected.div(selected.sum(axis=1), axis=0).fillna(0.0)
