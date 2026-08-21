"""``ClickHouseProvider`` - 查询分布式数据库 ClickHouse。

    依赖 ``clickhouse-driver``，为**可选依赖**，缺省时惰性报错。
    此处给出可用的查询实现；连接参数在实例化时传入。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import pandas as pd

from app.quantcore.data._util import require_optional
from app.quantcore.data.interface import IDataProvider

#: 默认行情表结构（与标准 OHLCV 对齐）
_DEFAULT_TABLE = "bars"


class ClickHouseProvider(IDataProvider):
    """从 ClickHouse 读取行情数据。"""

    name = "clickhouse"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9000,
        database: str = "default",
        table: str = _DEFAULT_TABLE,
        user: str = "default",
        password: str = "",
    ) -> None:
        ch = require_optional(
            "clickhouse_driver", "ClickHouseProvider 需要 clickhouse-driver"
        )
        self._Client = ch.Client
        self.client = ch.Client(
            host=host, port=port, database=database,
            user=user, password=password,
        )
        self.table = table

    def get_bars(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        cols = ",".join(fields) if fields else "open,high,low,close,volume"
        where = [f"symbol = '{symbol}'"]
        if start is not None:
            where.append(f"date >= '{start}'")
        if end is not None:
            where.append(f"date <= '{end}'")
        sql = (
            f"SELECT date, {cols} FROM {self.table} "
            f"WHERE {' AND '.join(where)} ORDER BY date"
        )
        rows, columns = self.client.execute(sql, with_column_types=True)
        df = pd.DataFrame(rows, columns=[c[0] for c in columns])
        df = df.set_index("date")
        df.index = pd.to_datetime(df.index)
        return df

    def get_universe(self, date: Optional[str] = None) -> List[str]:
        if date is None:
            sql = "SELECT DISTINCT symbol FROM universe ORDER BY symbol"
        else:
            sql = (
                "SELECT symbol FROM universe "
                f"WHERE date = '{date}' ORDER BY symbol"
            )
        rows = self.client.execute(sql)
        return [r[0] for r in rows]

    def get_symbols(self) -> List[str]:
        sql = f"SELECT DISTINCT symbol FROM {self.table} ORDER BY symbol"
        rows = self.client.execute(sql)
        return [r[0] for r in rows]
