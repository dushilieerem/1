"""研究股票池解析。"""

from __future__ import annotations

from typing import List, Optional
import pandas as pd

from app.models.data import Universe


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
