"""``WindProvider`` - 万得金融终端数据。

    依赖 ``WindPy``（万得商业授权客户端），为**可选依赖**，缺省时惰性报错。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import pandas as pd

from app.quantcore.data._util import require_optional
from app.quantcore.data.interface import IDataProvider


class WindProvider(IDataProvider):
    """通过 WindPy 读取万得行情数据。"""

    name = "wind"

    def __init__(self) -> None:
        windpy = require_optional(
            "WindPy", "WindProvider 需要 WindPy（万得金融终端），请安装 Wind 客户端"
        )
        self._w = windpy.w
        if not self._w.isconnected():
            self._w.start()

    def get_bars(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        fields = list(fields) if fields else ["open", "high", "low", "close", "volume"]
        # Wind 字段映射
        wind_fields = ",".join(fields)
        start = start.replace("-", "") if start else "20100101"
        end = end.replace("-", "") if end else "20991231"
        wind_code = f"{symbol}.SH" if symbol.startswith("6") else f"{symbol}.SZ"
        data = self._w.wsd(wind_code, wind_fields, start, end, "")
        df = pd.DataFrame(data.Data, index=fields).T
        df.index = pd.to_datetime(data.Times)
        df.index.name = "date"
        return df

    def get_universe(self, date: Optional[str] = None) -> List[str]:
        # 沪深 300 成分作为默认股票池示例
        date = date.replace("-", "") if date else ""
        data = self._w.wset("sectorconstituent", f"date={date};windcode=000300.SH")
        return [c.split(".")[0] for c in data.Data[1]]

    def get_symbols(self) -> List[str]:
        return self.get_universe()
