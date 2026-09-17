"""``AkShareProvider`` - A 股实时/历史数据（AkShare）。

    依赖 ``akshare``，为**可选依赖**，缺省时惰性报错。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import pandas as pd

from app.utils.imports import require_optional
from app.database.data.interface import IDataProvider

#: AkShare 返回列名 -> 标准字段
_AK_COL_MAP = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
}


class AkShareProvider(IDataProvider):
    """通过 AkShare 拉取 A 股日线行情。"""

    name = "akshare"

    def __init__(self, adjust: str = "qfq") -> None:
        self._ak = require_optional("akshare", "AkShareProvider 需要 akshare")
        self.adjust = adjust

    def get_bars(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        df = self._ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date=start.replace("-", "") if start else "20100101",
            end_date=end.replace("-", "") if end else "20991231",
            adjust=self.adjust,
        )
        df = df.rename(columns=_AK_COL_MAP)
        df = df.set_index("date")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        if fields is not None:
            df = df[list(fields)]
        return df

    def get_universe(self, date: Optional[str] = None) -> List[str]:
        # 沪深两市全部 A 股代码
        spot = self._ak.stock_zh_a_spot_em()
        return sorted(spot["代码"].astype(str).tolist())

    def get_symbols(self) -> List[str]:
        return self.get_universe()
