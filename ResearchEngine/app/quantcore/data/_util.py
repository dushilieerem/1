"""数据层共享工具。"""

from __future__ import annotations

from typing import List, Mapping, Optional, Union

import pandas as pd

#: universe 可为标的列表或股票池名称
Universe = Union[List[str], str]


def resolve_universe(
    data_provider,
    universe: Universe,
    as_of: Optional[str | pd.Timestamp] = None,
) -> List[str]:
    """将 universe 解析为标的列表。

    字符串视为股票池名；传入 ``as_of`` 时优先按该日的点时快照解析。
    不支持历史快照的 provider 继续回退到既有 ``get_universe`` 契约。
    """
    if isinstance(universe, str):
        resolver = getattr(data_provider, "get_universe_at", None)
        if as_of is not None and callable(resolver):
            return list(resolver(universe, as_of))
        return list(data_provider.get_universe(universe))
    return list(universe)


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


def require_optional(module: str, hint: str):
    """惰性导入可选依赖；缺失时抛出带安装提示的 ImportError。"""
    try:
        return __import__(module)
    except ImportError as exc:  # pragma: no cover
        raise ImportError(f"{hint}（请执行 `pip install {module}`）") from exc
