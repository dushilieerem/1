"""贵州茅台 13/26 日双均线趋势策略。"""

import pandas as pd


class Ma1326MaotaiStrategy:
    """快均线上穿慢均线时满仓持有贵州茅台，否则清仓。"""

    symbol = "600519.SH"
    fixed_symbols = (symbol,)

    def __init__(self, close: pd.DataFrame):
        self.close = close

    def generate_signals(self) -> pd.DataFrame:
        if self.symbol not in self.close.columns:
            raise ValueError(f"策略要求行情包含标的: {self.symbol}")

        price = self.close[self.symbol]
        fast = price.rolling(13).mean()
        slow = price.rolling(26).mean()
        target = pd.DataFrame(0.0, index=self.close.index, columns=self.close.columns)
        target.loc[fast > slow, self.symbol] = 1.0
        return target
