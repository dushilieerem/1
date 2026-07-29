"""截面动量策略：持有过去 20 日收益最高的十只股票。"""

import pandas as pd


class CrossSectionalMomentumStrategy:
    """每个交易日按 20 日动量排名并等权配置 Top10。"""

    def __init__(self, close: pd.DataFrame):
        self.close = close

    def generate_signals(self) -> pd.DataFrame:
        score = self.close.pct_change(20)
        selected = score.rank(axis=1, ascending=False, method="first").le(10) & score.notna()
        return selected.div(selected.sum(axis=1), axis=0).fillna(0.0)
