"""Dual Thrust 双重推力 A 股向量化研究策略。"""

from __future__ import annotations

import pandas as pd

from app.quantcore import BacktestSignals


class DualThrustAShareStrategy:
    """将当日盘中突破近似为当日收盘信号、下一交易日收益的研究策略。

    原始聚宽脚本在当日 09:45 读取盘中价格；当前向量化引擎只有日线 OHLC，
    因此这里使用当日收盘相对当日开盘触发线生成目标权重，并由 NativeEngine
    在下一交易日承担收益。该近似不宣称复现盘中成交。
    """

    execution_mode = "vectorized"

    def __init__(
        self,
        open: pd.DataFrame,
        high: pd.DataFrame,
        low: pd.DataFrame,
        close: pd.DataFrame,
        amount: pd.DataFrame,
        market_cap: pd.DataFrame,
        range_n: int = 4,
        k1: float = 0.5,
        k2: float = 0.5,
        max_holdings: int = 10,
        pool_size: int = 40,
        avg_amount_days: int = 20,
        min_market_cap: float = 3_000_000_000.0,
        listed_days: pd.DataFrame | None = None,
        min_listed_days: int = 365,
    ) -> None:
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.amount = amount
        self.market_cap = market_cap
        self.range_n = range_n
        self.k1 = k1
        self.k2 = k2
        self.max_holdings = max_holdings
        self.pool_size = pool_size
        self.avg_amount_days = avg_amount_days
        self.min_market_cap = min_market_cap
        self.listed_days = listed_days
        self.min_listed_days = min_listed_days

    def generate_signals(self) -> BacktestSignals:
        open_, high, low, close, amount, market_cap, listed_days = self._aligned()
        if self.range_n < 1 or self.max_holdings < 1 or self.pool_size < 1:
            raise ValueError("Dual Thrust 的窗口和持仓参数必须为正数")

        width = self._range(high, low, close, self.range_n)
        buy_line = open_ + self.k1 * width
        sell_line = open_ - self.k2 * width
        liquidity = amount.rolling(self.avg_amount_days, min_periods=self.avg_amount_days).mean().shift(1)
        cap_as_of = market_cap.shift(1)
        listed_as_of = listed_days.shift(1) if listed_days is not None else None

        target = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        positions: set[str] = set()
        pool: list[str] = []
        weight = 1.0 / self.max_holdings

        for index, date in enumerate(close.index):
            if date.weekday() == 0:
                liquidity_row = liquidity.loc[date]
                cap_row = cap_as_of.loc[date]
                eligible = liquidity_row.notna() & cap_row.ge(self.min_market_cap)
                if listed_as_of is not None:
                    eligible &= listed_as_of.loc[date].ge(self.min_listed_days)
                pool = (
                    liquidity_row[eligible]
                    .sort_values(ascending=False)
                    .head(self.pool_size)
                    .index.tolist()
                )

            sell_row, buy_row, close_row = sell_line.loc[date], buy_line.loc[date], close.loc[date]
            for symbol in tuple(positions):
                if pd.notna(sell_row[symbol]) and pd.notna(close_row[symbol]) and close_row[symbol] <= sell_row[symbol]:
                    positions.remove(symbol)

            for symbol in pool[: self.max_holdings]:
                if symbol in positions:
                    continue
                if pd.notna(buy_row[symbol]) and pd.notna(close_row[symbol]) and close_row[symbol] >= buy_row[symbol]:
                    positions.add(symbol)

            if positions:
                target.loc[date, list(positions)] = weight

        return BacktestSignals(target_weights=target, close=close)

    def _aligned(self):
        frames = [self.open, self.high, self.low, self.amount, self.market_cap]
        if self.listed_days is not None:
            frames.append(self.listed_days)
        dates = self.close.index
        symbols = self.close.columns
        for frame in frames:
            dates = dates.intersection(frame.index)
            symbols = symbols.intersection(frame.columns)
        if dates.empty or symbols.empty:
            raise ValueError("Dual Thrust 没有可对齐的行情或基本面数据")
        close = self.close.loc[dates, symbols].sort_index()
        return tuple(
            frame.loc[dates, symbols].sort_index()
            for frame in [self.open, self.high, self.low, close, self.amount, self.market_cap]
        ) + (self.listed_days.loc[dates, symbols].sort_index() if self.listed_days is not None else None,)

    @staticmethod
    def _range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, window: int) -> pd.DataFrame:
        hh = high.shift(1).rolling(window, min_periods=window).max()
        lc = close.shift(1).rolling(window, min_periods=window).min()
        hc = close.shift(1).rolling(window, min_periods=window).max()
        ll = low.shift(1).rolling(window, min_periods=window).min()
        first = hh - lc
        second = hc - ll
        return first.where(first >= second, second)
