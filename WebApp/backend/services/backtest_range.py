# -*- coding: utf-8 -*-
"""预设周期 → RE 接受的 start/end（RE 已移除 backtest_period）。

同事 RE 行情当前只到 2026-01-01；预设周期均以该日为 end 往前推，
避免用「今天」导致区间落在无数据段。RE 数据更新后改 RE_MARKET_END 或环境变量即可。
"""
from __future__ import annotations

import calendar
import os
from datetime import datetime, timedelta


def re_market_end() -> datetime:
    """RE 可用行情截止日；可用环境变量 RE_MARKET_END=YYYY-MM-DD 覆盖。"""
    raw = (os.environ.get("RE_MARKET_END") or "").strip()
    if raw:
        return datetime.strptime(raw[:10], "%Y-%m-%d")
    return datetime(2026, 1, 1)


def period_to_start_end(period: str, *, end: datetime | None = None) -> tuple[str, str]:
    end_dt = end or re_market_end()
    y, m, d = end_dt.year, end_dt.month, end_dt.day
    if period == "1d":
        start_dt = end_dt - timedelta(days=1)
    elif period == "5d":
        start_dt = end_dt - timedelta(days=5)
    elif period == "10d":
        start_dt = end_dt - timedelta(days=10)
    elif period == "1m":
        m -= 1
        while m <= 0:
            m += 12
            y -= 1
        d = min(d, calendar.monthrange(y, m)[1])
        start_dt = datetime(y, m, d)
    elif period == "6m":
        m -= 6
        while m <= 0:
            m += 12
            y -= 1
        d = min(d, calendar.monthrange(y, m)[1])
        start_dt = datetime(y, m, d)
    elif period == "3m":
        m -= 3
        while m <= 0:
            m += 12
            y -= 1
        d = min(d, calendar.monthrange(y, m)[1])
        start_dt = datetime(y, m, d)
    elif period == "1y":
        start_dt = datetime(y - 1, m, d)
    elif period == "3y":
        start_dt = datetime(y - 3, m, d)
    else:
        raise ValueError(f"unsupported period: {period}")
    fmt = lambda dt: dt.strftime("%Y-%m-%d")
    return fmt(start_dt), fmt(end_dt)


def build_factor_backtest_payload(
    *,
    factor_code: str,
    factor_name: str,
    universe: str = "CSI300",
    period: str = "3y",
    filter_limit_up: bool = True,
    filter_suspended: bool = True,
    portfolio_type: str = "long_short",
    groups: int = 5,
    rebalance_days: int = 20,
    benchmark: str | None = None,
    analysis_level: str = "core",
    end: datetime | None = None,
) -> dict:
    start_s, end_s = period_to_start_end(period, end=end)
    return {
        "factor_code": factor_code,
        "factor_name": factor_name,
        "portfolio_type": portfolio_type,
        "universe": universe,
        "start": start_s,
        "end": end_s,
        "filter_limit_up": filter_limit_up,
        "filter_suspended": filter_suspended,
        "groups": groups,
        "rebalance_days": rebalance_days,
        "benchmark": benchmark or universe,
        "analysis_level": analysis_level,
    }
