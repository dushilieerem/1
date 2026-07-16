"""``ICalendar`` 的默认实现，提炼自 ``build_factor_portfolio._rebalance_mask``。

交易日 / 调仓日的判断本就是量化回测的通用件，单独成接口便于未来接入真实交易日历
（akshare / 交易所日历）与多市场扩展（BC6 Market Rule）。
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from quantcore.backtest.adapter.interfaces import ICalendar


class PandasCalendar(ICalendar):
    """基于 DatetimeIndex 的朴素交易日历。

    「交易日」即面板里出现过的日期；调仓日按 ``freq``（daily/weekly/monthly）取每周期首个。
    与既有 ``_rebalance_mask`` 行为逐位一致。
    """

    def rebalance_mask(self, index: pd.DatetimeIndex, freq: str | int) -> pd.Series:
        """生成布尔序列，标记每个日期是否为调仓日（首日必为调仓日）。"""
        if isinstance(freq, int):
            if freq < 1:
                raise ValueError(f"调仓间隔至少为 1 个交易日，得到 {freq}")
            mask = pd.Series(False, index=index)
            mask.iloc[::freq] = True
            return mask
        if freq in ("daily", "d", "1d"):
            return pd.Series(True, index=index)
        if freq in ("weekly", "w"):
            iso = index.isocalendar()
            year_week = pd.Series(list(zip(iso.year, iso.week)), index=index)
            return ~year_week.duplicated()
        if freq in ("monthly", "m"):
            ym = pd.Series(index.year * 100 + index.month, index=index)
            return ~ym.duplicated()
        # 默认每月
        ym = pd.Series(index.year * 100 + index.month, index=index)
        return ~ym.duplicated()

    def is_trading_day(self, date) -> bool:
        # 朴素实现：仅当 date 在已知交易日集合内。无外部日历时退化为「非 NaT 即可」
        ts = pd.Timestamp(date)
        return bool(pd.notna(ts))

    def trading_days(self, start: Optional[str] = None, end: Optional[str] = None) -> pd.DatetimeIndex:
        # 朴素实现：按工作日生成（真实交易日历应在 IDataFeed 层提供）
        return pd.bdate_range(start=start or "2000-01-01", end=end or pd.Timestamp.today())
