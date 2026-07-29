"""双均线趋势策略：快均线上穿慢均线时等权持有。"""

import pandas as pd


class DualMovingAverageStrategy:
    """使用 20/60 日均线识别趋势，只依赖收盘价。"""

    def __init__(self, close: pd.DataFrame):
        self.close = close

    def generate_signals(self) -> pd.DataFrame:
        fast = self.close.rolling(20).mean()
        slow = self.close.rolling(60).mean()
        selected = fast.gt(slow)
        return selected.div(selected.sum(axis=1), axis=0).fillna(0.0)
