"""数据层共享工具。"""

from __future__ import annotations

from typing import Mapping, Optional

import pandas as pd





def first_panel_date(panels: Mapping[str, pd.DataFrame]) -> Optional[pd.Timestamp]:
    """返回已按回测区间过滤后的首个实际行情日。"""
    if "close" in panels:
        close = panels["close"]
        if not close.empty:
            return pd.Timestamp(close.index[0])
    for field in panels:
        if field == "close":
            continue
        frame = panels[field]
        if not frame.empty:
            return pd.Timestamp(frame.index[0])
    return None


def filter_by_date(
    df: pd.DataFrame,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """按日期索引闭区间过滤。"""
    if start is not None:
        df = df.loc[df.index >= pd.to_datetime(start)]
    if end is not None:
        df = df.loc[df.index <= pd.to_datetime(end)]
    return df

