"""行情面板数据模型。"""

from __future__ import annotations

from typing import Callable, List, Union
import pandas as pd

Universe = Union[List[str], str]


class IndexPanel:
    """单个指数的日线行情。"""

    def __init__(self, data: pd.DataFrame) -> None:
        for field in ("open", "high", "low", "close", "volume"):
            if field in data:
                setattr(self, field, data[field])


class Panel:
    """字段面板：``{field: DataFrame[日期×标的]}`` 的封装。

    通过属性访问常用字段（``data.close``）或下标访问任意字段
   （``data["current_mv"]``）。

    ``fields`` 可为具体 dict，也可为懒加载的 Mapping（如 FieldParquet 的
    _LazyPanels）-- 仅在字段被访问时才真正读盘。``symbols`` 给定时按 universe
    过滤列（同样懒执行 + 缓存）。
    """

    def __init__(
        self,
        fields,
        symbols=None,
        index_loader: Callable[[str], pd.DataFrame] | None = None,
        mask: pd.DataFrame | None = None,
    ) -> None:
        # 用 object.__setattr__ 绕过自定义 __getattr__，避免属性查找回环
        object.__setattr__(self, "_fields", fields)
        object.__setattr__(self, "_symbols", symbols)
        object.__setattr__(self, "_cache", {})
        object.__setattr__(self, "_index_loader", index_loader)
        object.__setattr__(self, "_index_cache", {})
        object.__setattr__(self, "_mask", mask)

    def _get(self, name: str) -> pd.DataFrame:
        cache = object.__getattribute__(self, "_cache")
        if name in cache:
            return cache[name]
        fields = object.__getattribute__(self, "_fields")
        if name not in fields:
            raise AttributeError(
                f"Panel 无字段 {name!r}，可用字段: {list(fields)}"
            )
        symbols = object.__getattribute__(self, "_symbols")
        get_view = getattr(fields, "get_view", None)
        if callable(get_view):
            df = get_view(name, symbols)
        else:
            df = fields[name]
            if symbols is not None and not df.columns.equals(pd.Index(symbols)):
                df = df.reindex(columns=symbols)
        mask = object.__getattribute__(self, "_mask")
        if mask is not None:
            df = df.mask(~mask.reindex(index=df.index, columns=df.columns).fillna(False))
        cache[name] = df
        return df

    def with_mask(self, mask: pd.DataFrame | None, *, enabled: bool = True) -> "Panel":
        """返回是否应用样本掩码的独立 Panel 视图，不修改原始行情。"""

        return Panel(
            object.__getattribute__(self, "_fields"),
            symbols=object.__getattribute__(self, "_symbols"),
            index_loader=object.__getattribute__(self, "_index_loader"),
            mask=mask if enabled else None,
        )

    def __getattr__(self, name: str) -> pd.DataFrame:
        return self._get(name)

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self._get(name)

    def index(self, name: str) -> IndexPanel:
        """按名称懒加载指数行情。"""
        cache = object.__getattribute__(self, "_index_cache")
        name = name.upper()
        if name not in cache:
            loader = object.__getattribute__(self, "_index_loader")
            if loader is None:
                raise AttributeError("当前数据源不支持指数行情")
            cache[name] = IndexPanel(loader(name))
        return cache[name]

    def __contains__(self, name: str) -> bool:
        return name in object.__getattribute__(self, "_fields")

    @property
    def fields(self) -> list:
        """所有可用字段名。"""
        return list(object.__getattribute__(self, "_fields"))

    @property
    def symbols(self) -> "pd.Index":
        """标的列表（取首个字段的列）。"""
        first = next(iter(object.__getattribute__(self, "_fields")))
        return self._get(first).columns

    @property
    def dates(self) -> "pd.Index":
        """日期索引。"""
        first = next(iter(object.__getattribute__(self, "_fields")))
        return self._get(first).index

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Panel fields={self.fields}>"


class DataView:
    """仅暴露截至上一交易日收盘的日线数据。"""

    def __init__(self, panels: dict[str, pd.DataFrame]) -> None:
        self._panels = panels
        self._as_of: pd.Timestamp | None = None

    def set_as_of(self, timestamp: pd.Timestamp | None) -> None:
        self._as_of = timestamp

    @property
    def symbols(self) -> list[str]:
        return list(self._panels["close"].columns)

    @property
    def fields(self) -> frozenset[str]:
        return frozenset(self._panels)

    def history(self, symbols: list[str], fields: list[str], count: int) -> dict[str, pd.DataFrame]:
        if self._as_of is None:
            return {field: self._panels[field].iloc[0:0].reindex(columns=symbols) for field in fields}
        return {
            field: self._panels[field].loc[:self._as_of, symbols].tail(count).copy()
            for field in fields
        }
