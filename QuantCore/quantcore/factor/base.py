"""``Panel`` + ``BaseFactor`` - 面板因子抽象基类（VectorEngine 模型）。

依据 ``docs/05-architecture/engine-design.md §2`` VectorEngine：因子在整张 ``日期×标的``
宽表上一次性向量化计算，**不逐只循环**。这与 ResearchEngine 的宽表数据形态一致。

**契约**：

- ``BaseFactor.compute(data: Panel) -> pd.DataFrame``
- ``data`` 是 :class:`Panel`，封装了各字段的 ``日期×标的`` 宽表，通过
  ``data.close`` / ``data.open`` / ``data["market_cap"]`` 等访问。
- 返回 ``日期×标的`` 的因子值宽表。

研究员只写 ``compute``，不关心后端与引擎代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict

import pandas as pd


class IndexPanel:
    """单个指数的日线行情。"""

    def __init__(self, data: pd.DataFrame) -> None:
        for field in ("open", "high", "low", "close", "volume"):
            if field in data:
                setattr(self, field, data[field])


class Panel:
    """字段面板：``{field: DataFrame[日期×标的]}`` 的封装。

    通过属性访问常用字段（``data.close``）或下标访问任意字段
   （``data["market_cap"]``）。

    ``fields`` 可为具体 dict，也可为懒加载的 Mapping（如 FieldParquet 的
    _LazyPanels）-- 仅在字段被访问时才真正读盘。``symbols`` 给定时按 universe
    过滤列（同样懒执行 + 缓存）。
    """

    def __init__(
        self,
        fields,
        symbols=None,
        index_loader: Callable[[str], pd.DataFrame] | None = None,
    ) -> None:
        # 用 object.__setattr__ 绕过自定义 __getattr__，避免属性查找回环
        object.__setattr__(self, "_fields", fields)
        object.__setattr__(self, "_symbols", symbols)
        object.__setattr__(self, "_cache", {})
        object.__setattr__(self, "_index_loader", index_loader)
        object.__setattr__(self, "_index_cache", {})

    def _get(self, name: str) -> pd.DataFrame:
        cache = object.__getattribute__(self, "_cache")
        if name in cache:
            return cache[name]
        fields = object.__getattribute__(self, "_fields")
        if name not in fields:
            raise AttributeError(
                f"Panel 无字段 {name!r}，可用字段: {list(fields)}"
            )
        df = fields[name]
        symbols = object.__getattribute__(self, "_symbols")
        if symbols is not None:
            df = df.reindex(columns=symbols)
        cache[name] = df
        return df

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


class BaseFactor(ABC):
    """因子基类（面板模式）。研究员继承本类并实现 :meth:`compute`。"""

    #: 因子名称
    name: str = "base"
    #: 因子作者
    author: str = "anonymous"
    #: 因子参数
    params: Dict[str, Any] = {}

    def __init__(self, name: str | None = None, author: str | None = None,
                 params: Dict[str, Any] | None = None) -> None:
        if name is not None:
            self.name = name
        if author is not None:
            self.author = author
        if params is not None:
            self.params = {**self.params, **params}

    @abstractmethod
    def compute(self, data: Panel) -> pd.DataFrame:
        """因子核心计算逻辑（一次向量化算完整张宽表）。

        Parameters
        ----------
        data:
            :class:`Panel`，含各字段的 ``日期×标的`` 宽表。

        Returns
        -------
        pandas.DataFrame
            ``日期×标的`` 的因子值宽表。
        """

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} name={self.name!r} author={self.author!r}>"


class _MethodFactor(BaseFactor):
    """把因子库的一个方法适配为 :class:`BaseFactor`（引擎内部用）。

    计算时把面板绑定到库实例，再调用方法（方法内用 ``self.close`` 等访问数据）。
    """

    def __init__(self, name, author, library, method, params=None):
        super().__init__(name=name, author=author)
        self._library = library
        self._method = method
        self.params = dict(params) if params else {}

    def compute(self, data: Panel) -> pd.DataFrame:
        self._library._panel = data  # 绑定数据，方法内 self.close 可用
        return self._method(**self.params)


class FactorLibrary:
    """因子库基类。

    研究员继承本类、设一次 ``author``，然后把每个因子写成一个**方法**即可：

    ::

        class MyLib(FactorLibrary):
            author = "张三"

            def myalpha(self, window=5):
                return self.close - self.close.rolling(window).mean()

    约定：

    - 每个公开方法（不以 ``_`` 开头）即一个因子，因子名=方法名；
    - 方法内通过 ``self.<字段>`` 访问当前面板字段（引擎计算时自动绑定数据），
      可用字段对齐 MarketData：

      - 价格：``self.open`` / ``self.high`` / ``self.low`` / ``self.close``
      - 成交：``self.volume`` / ``self.amount`` / ``self.turnover``
      - 股本市值：``self.total_shares`` / ``self.float_shares``
        / ``self.total_mv`` / ``self.float_mv``
      - 估值：``self.pe_ttm`` / ``self.pb`` / ``self.ps_ttm``
      - 布尔：``self.is_st`` / ``self.limit_up``

      - 指数：``self.csi300.close`` / ``self.csi500.close`` /
        ``self.csi1000.close`` / ``self.sse50.close``（日线 Series）

      股票字段为 ``日期×标的`` 宽表，指数为按日期索引的 Series；均按需懒加载。
      不在列表里的股票字段用 ``self["字段"]``。
    - 方法的参数（如 ``window``）即因子参数，带默认值；
    - 辅助方法用 ``_`` 前缀，不会被当成因子。
    """

    #: 因子库作者——本库所有因子共用此作者
    author: str = "anonymous"

    #: 当前面板（计算时由引擎绑定，外部不要直接设）
    _panel: "Panel | None" = None

    # -- 面板字段访问（对齐 MarketData；均为 日期×标的 宽表，按需懒加载）--
    # 价格
    @property
    def open(self) -> pd.DataFrame:  # noqa: A003
        return self._panel.open

    @property
    def high(self) -> pd.DataFrame:
        return self._panel.high

    @property
    def low(self) -> pd.DataFrame:
        return self._panel.low

    @property
    def close(self) -> pd.DataFrame:
        return self._panel.close

    # 成交
    @property
    def volume(self) -> pd.DataFrame:
        return self._panel.volume

    @property
    def amount(self) -> pd.DataFrame:
        return self._panel.amount

    @property
    def turnover(self) -> pd.DataFrame:
        return self._panel.turnover

    # 股本 / 市值
    @property
    def total_shares(self) -> pd.DataFrame:
        return self._panel.total_shares

    @property
    def float_shares(self) -> pd.DataFrame:
        return self._panel.float_shares

    @property
    def total_mv(self) -> pd.DataFrame:
        """总市值（元）。"""
        return self._panel.total_mv

    @property
    def float_mv(self) -> pd.DataFrame:
        """流通市值（元）。"""
        return self._panel.float_mv

    # 估值
    @property
    def pe_ttm(self) -> pd.DataFrame:
        """滚动市盈率。"""
        return self._panel.pe_ttm

    @property
    def pb(self) -> pd.DataFrame:
        """市净率。"""
        return self._panel.pb

    @property
    def ps_ttm(self) -> pd.DataFrame:
        """滚动市销率。"""
        return self._panel.ps_ttm

    # 布尔（Int8：1/0/<NA>）
    @property
    def is_st(self) -> pd.DataFrame:
        """是否 ST。"""
        return self._panel.is_st

    @property
    def limit_up(self) -> pd.DataFrame:
        """是否涨停。"""
        return self._panel.limit_up

    # 指数（日线 Series，按交易日索引）
    @property
    def csi300(self) -> IndexPanel:
        return self._panel.index("CSI300")

    @property
    def csi500(self) -> IndexPanel:
        return self._panel.index("CSI500")

    @property
    def csi1000(self) -> IndexPanel:
        return self._panel.index("CSI1000")

    @property
    def sse50(self) -> IndexPanel:
        return self._panel.index("SSE50")

    @property
    def fields(self) -> list:
        """当前面板可用字段名。"""
        return self._panel.fields

    def __getitem__(self, key: str) -> pd.DataFrame:
        """下标访问任意字段（如 ``self["pe_ttm"]``）。"""
        return self._panel[key]

    def _factor_methods(self) -> "dict[str, object]":
        """返回本库所有公开方法（因子）。"""
        import inspect

        return {
            name: member
            for name, member in inspect.getmembers(self, predicate=inspect.ismethod)
            if not name.startswith("_")
        }


def library_factors(library: "FactorLibrary") -> "dict[str, _MethodFactor]":
    """从因子库实例提取所有因子方法，返回 ``{因子名: _MethodFactor}``。"""
    return {
        name: _MethodFactor(name, library.author, library, method)
        for name, method in library._factor_methods().items()
    }
