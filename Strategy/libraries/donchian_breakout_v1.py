"""唐奇安突破策略：仅持有创 60 日新高的股票。"""

import pandas as pd


class DonchianBreakoutStrategy:
    """以收盘价突破过去 60 日高点作为趋势入场信号。"""

    def __init__(self, close: pd.DataFrame):
        self.close = close

    def generate_signals(self) -> pd.DataFrame:
        channel_high = self.close.rolling(60, min_periods=60).max()
        selected = self.close.ge(channel_high) & channel_high.notna()
        return selected.div(selected.sum(axis=1), axis=0).fillna(0.0)
