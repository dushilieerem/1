"""``Panel`` + ``BaseFactor`` - 面板因子抽象基类（VectorEngine 模型）。

依据 ``docs/02-架构文档/engine-design.md §2`` VectorEngine：因子在整张 ``日期×标的``
宽表上一次性向量化计算，**不逐只循环**。这与 app 的宽表数据形态一致。

**契约**：

- ``BaseFactor.compute(data: Panel) -> pd.DataFrame``
- ``data`` 是 :class:`Panel`，封装了各字段的 ``日期×标的`` 宽表，通过
  ``data.close`` / ``data.open`` / ``data["current_mv"]`` 等访问。
- 返回 ``日期×标的`` 的因子值宽表。

研究员只写 ``compute``，不关心后端与引擎代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import copy
from typing import Any, Callable, Dict

import pandas as pd

from app.models.data import Panel, IndexPanel






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
        # 一个库实例的多个方法可能在 ExperimentManager 的不同 Worker 中同时
        # 计算；不能再通过共享实例上的 `_panel` 绑定当前数据。
        library = copy.copy(self._library)
        for name, value in vars(self._library).items():
            if isinstance(value, dict):
                setattr(library, name, value.copy())
            elif isinstance(value, list):
                setattr(library, name, list(value))
            elif isinstance(value, set):
                setattr(library, name, set(value))
        library._panel = data

        bound_to_library = getattr(self._method, "__self__", None) is self._library
        method_func = getattr(self._method, "__func__", None)
        if bound_to_library and method_func is not None:
            method = method_func.__get__(library, type(library))
        else:  # BaseFactor 等非库因子保持原有行为
            method = self._method
        return method(**self.params)


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
      - 市值：``self.current_mv``
      - 估值：``self.dividend_yield_ttm`` / ``self.pe_ttm`` /
        ``self.pb_mrq`` / ``self.pcf_operating_cash_flow_ttm``
      - 状态：``self.listed_status`` / ``self.the_sw_industry_code`` /
        ``self.up_and_down_status``

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

    # 市值
    @property
    def current_mv(self) -> pd.DataFrame:
        """iFinD current market value（元）。"""
        return self._panel.current_mv

    # 估值
    @property
    def dividend_yield_ttm(self) -> pd.DataFrame:
        """滚动十二个月股息率。"""
        return self._panel.dividend_yield_ttm

    @property
    def pb_mrq(self) -> pd.DataFrame:
        """最近报告期市净率。"""
        return self._panel.pb_mrq

    @property
    def pcf_operating_cash_flow_ttm(self) -> pd.DataFrame:
        """经营现金流滚动十二个月市现率。"""
        return self._panel.pcf_operating_cash_flow_ttm

    @property
    def pe_ttm(self) -> pd.DataFrame:
        """滚动十二个月市盈率。"""
        return self._panel.pe_ttm

    # 状态
    @property
    def listed_status(self) -> pd.DataFrame:
        """上市状态原始文本。"""
        return self._panel.listed_status

    @property
    def the_sw_industry_code(self) -> pd.DataFrame:
        """申万行业代码。"""
        return self._panel.the_sw_industry_code

    @property
    def up_and_down_status(self) -> pd.DataFrame:
        """涨跌停及停牌状态原始文本。"""
        return self._panel.up_and_down_status

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
