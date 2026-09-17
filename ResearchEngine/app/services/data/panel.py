"""因子与策略计算使用的 MarketData release 视图。"""

from __future__ import annotations

import pandas as pd

from app.models.market_data import MarketDataRelease


class ResearchDataPanel:
    """连接业务域数据对象与因子计算表达式的只读视图。

    业务域访问使用 ``data.stock.close``、``data.basic.pb_mrq`` 和
    ``data.status.up_and_down_status``；为保持因子表达式简洁，``data.close`` 等
    平铺属性仍直接返回原生 DataFrame，不额外包装 Pandas 对象。
    """

    def __init__(self, release: MarketDataRelease) -> None:
        self.release = release

    @property
    def stock(self):
        return self.release.stock

    @property
    def basic(self):
        return self.release.basic

    @property
    def status(self):
        return self.release.status

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(self.release.fields)

    def __contains__(self, name: str) -> bool:
        return name in self.release.fields

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self._field(name)

    def __getattr__(self, name: str) -> pd.DataFrame:
        return self._field(name)

    def _field(self, name: str) -> pd.DataFrame:
        try:
            return self.release.fields[name]
        except KeyError as exc:
            raise AttributeError(f"ResearchDataPanel 无字段 {name!r}") from exc
