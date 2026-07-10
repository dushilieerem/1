"""数据层共享工具。"""

from __future__ import annotations

from typing import List, Optional, Union

import pandas as pd

#: universe 可为标的列表或股票池名称
Universe = Union[List[str], str]


def resolve_universe(data_provider, universe: Universe) -> List[str]:
    """将 universe 解析为标的列表。

    字符串视为股票池名，委托 ``provider.get_universe`` 解析；列表原样返回。
    """
    if isinstance(universe, str):
        return list(data_provider.get_universe(universe))
    return list(universe)


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
