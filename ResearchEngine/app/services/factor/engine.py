"""``FactorEngine`` - 面板因子计算引擎（VectorEngine 模型）。

依据 ``docs/99-历史归档/FEAT-001-QuantCore基础能力/04-class-design.md`` FactorEngine 节与 ``docs/02-架构文档/engine-design.md §2``：

    属性：
      factors: Dict[str, BaseFactor]

    方法：
      register(factor: BaseFactor)
      compute(factor_name, data_provider, universe, start, end) -> pd.DataFrame
      compute_all(...) -> Dict[str, pd.DataFrame]

运行流程（**面板模式，一次算完，不逐只循环**）：

    ① factor = self.factors[factor_name]
    ② panels = data_provider.get_panels(start, end)   # {field: 日期×标的 宽表}
    ③ 按 universe 过滤列
    ④ factor.compute(Panel(panels))                    # 一次向量化
    ⑤ 返回 日期×标的 因子宽表

**关键原则**：Research 只写 ``factor.compute(data)``，不关心后端与引擎代码。
本引擎不计算 IC 等指标（IC 由 MetricEngine 统一负责）。
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any, Dict, Optional, Sequence

import pandas as pd

from app.models.data import Universe
from app.models.factor_backtest import FactorBacktestSpec
from app.utils.data import first_panel_date
from app.services.data.universe import resolve_universe
from app.services.factor.backend import ComputeBackend, get_backend
from app.services.factor.base import BaseFactor, FactorLibrary, library_factors
from app.services.factor.errors import FactorBacktestDataError, FactorBacktestParameterError
from app.services.data.engine import DataEngine
from app.models.data import Panel
from app.services.factor.tool import preprocess_factor_values


_LOGGER = logging.getLogger(__name__)


def _normalize_factor_output(factor: BaseFactor, values) -> pd.DataFrame:
    """把 compute 的返回值规整为 ``日期×标的`` 宽表 DataFrame。"""
    if isinstance(values, pd.Series):
        values = values.to_frame(name=factor.name)
    values = pd.DataFrame(values)
    values.index.name = "date"
    return values


class FactorEngine:
    """面板因子计算引擎。

    ``FactorEngine`` 同时是因子运行时的注册表、来源解析门面和计算门面。
    回测规格交给 ``_resolve_factor`` 后，由引擎根据因子名、因子库和源码
    加载或生成本次任务私有的 ``self._factor``；具体来源实现仍可通过
    ``factor_loader`` 注入替换。

    ``factor_loader`` 参数是一个很小的适配边界，而不是新的因子对象层：

    - 优先调用 ``loader.load_factor(source=..., ...)``；
    - 兼容可调用对象（``loader(source=..., ...)``）；
    - 兼容现有文件加载器的 ``loader.load(module_name)`` API。

    这样数据库迁移时只需替换 loader，不需要改动 ``compute``、
    ``FactorBacktestSpec`` 或因子类本身。
    """

    def __init__(
        self,
        spec: FactorBacktestSpec | None = None,
        backend: ComputeBackend | str = "python",
        *,
        factor_loader: Any | None = None,
    ) -> None:
        self.factors: Dict[str, BaseFactor] = {}
        if isinstance(backend, str):
            backend = get_backend(backend)
        self.backend: ComputeBackend = backend
        self._factor_loader = factor_loader
        self._factor: BaseFactor | None = None
        self.spec: FactorBacktestSpec | None = None
        self.actual_end: str | None = None
        self.panels = None
        self._panel: Panel | None = None
        self.eligibility_mask: pd.DataFrame | None = None
        self._filter_info: dict[str, Any] = {"mask": None, "status": {}, "warnings": []}
        if spec is not None:
            self._prepare_spec(spec)

    def _prepare_spec(self, spec: FactorBacktestSpec) -> None:
        """初始化本次因子任务的私有数据、样本条件和因子实例。"""
        if not isinstance(spec, FactorBacktestSpec):
            raise FactorBacktestParameterError("FactorEngine 只接受 FactorBacktestSpec")
        data_engine = DataEngine.get_instance()
        # 先从共享只读面板取得 close 的日期和股票池解析依据；随后才按
        # universe 创建任务私有列切片。旧实现先深拷贝全市场 close，再在
        # Panel 中按股票池重切，长历史上会产生一次无用的大矩阵复制。
        if isinstance(data_engine, DataEngine):
            try:
                preview = data_engine.get_panels(
                    spec.start,
                    spec.end,
                    fields=["close"],
                )
                close = preview["close"]
            except (KeyError, TypeError) as exc:
                raise FactorBacktestDataError("回测区间没有可用 close 数据") from exc
        else:
            # 保留测试替身及旧 provider 的最小读取契约。
            panels = data_engine.get_task_panels(spec.start, spec.end)
            try:
                close = panels["close"]
            except (KeyError, TypeError) as exc:
                raise FactorBacktestDataError("回测区间没有可用 close 数据") from exc
        if close is None or close.empty:
            raise FactorBacktestDataError("当前数据版本没有可用 close 数据")
        self.actual_end = pd.Timestamp(close.index.max()).date().isoformat()
        if spec.start is not None and pd.Timestamp(spec.start) > pd.Timestamp(self.actual_end):
            raise FactorBacktestParameterError("回测 start 不能晚于 end")
        self.spec = spec
        symbols = resolve_universe(
            data_engine, spec.universe, as_of=pd.Timestamp(close.index[0])
        )
        if isinstance(data_engine, DataEngine):
            panels = data_engine.get_task_panels(
                spec.start,
                spec.end,
                symbols=symbols,
            )
        self.panels = panels
        self._panel = Panel(
            panels,
            symbols=symbols,
            index_loader=lambda name: data_engine.get_index(name, spec.start, spec.end),
        )
        if spec.filter_suspended or spec.filter_limit_up:
            self._filter_info = data_engine.build_filter_mask(
                self._panel,
                filter_suspended=spec.filter_suspended,
                filter_limit_up=spec.filter_limit_up,
            )
        else:
            # 无过滤时不要创建与行情同样大小的全 True 掩码，也不要为了
            # 构造该掩码再触发一次 close 字段的任务副本。
            self._filter_info = {
                "mask": None,
                "status": {
                    "is_suspended": "disabled",
                    "limit_up": "disabled",
                },
                "warnings": [],
            }
        self.eligibility_mask = self._filter_info["mask"]
        self._log_filter_diagnostics()
        self._resolve_factor(spec)

    def _log_filter_diagnostics(self) -> None:
        """记录本次样本过滤的实际状态与可选字段告警。"""

        for name, status in self._filter_info["status"].items():
            _LOGGER.info("因子样本过滤 %s: %s", name, status)
        for warning in self._filter_info["warnings"]:
            _LOGGER.warning("因子样本过滤告警: %s", warning)

    def result_diagnostics(self) -> dict[str, Any]:
        """返回可写入结果与缓存的过滤诊断副本。"""

        return {
            "filter_status": dict(self._filter_info["status"]),
            "warnings": list(self._filter_info["warnings"]),
        }

    def has_market_field(self, name: str) -> bool:
        """本次任务是否已加载指定市场字段。"""

        return self._panel is not None and name in self._panel

    def market_field(self, name: str, *, use_mask: bool = False) -> pd.DataFrame:
        """返回本次任务所需的一个行情字段，而不暴露内部 ``Panel``。

        ``use_mask`` 只用于需要按研究样本查看行情的调用方；因子计算本身始终
        在原始面板上完成，再由 ``preprocess`` 应用掩码，避免过滤改变滚动窗口。
        """

        if self._panel is None:
            raise FactorBacktestParameterError("FactorEngine 尚未完成回测任务初始化")
        panel = self._panel.with_mask(self.eligibility_mask, enabled=use_mask)
        return panel[name]

    def _compute_factor_value(self) -> pd.DataFrame:
        """计算并加工构造时加载的因子，返回本次任务的因子值。"""
        if self._panel is None or self.spec is None or self._factor is None:
            raise FactorBacktestParameterError("FactorEngine 尚未完成回测任务初始化")
        values = self.backend.execute(self._factor.compute, self._panel)
        raw = _normalize_factor_output(self._factor, values)
        return self.preprocess(
            raw,
            eligibility_mask=self.eligibility_mask,
            winsorize=self.spec.winsorize,
            standardize=self.spec.standardize,
        )

    def set_factor_loader(self, loader: Any | None) -> None:
        """设置或替换因子加载器。

        loader 采用结构化鸭子类型，不要求 QuantCore 依赖 ResearchEngine 的
        文件、数据库实现。传入 ``None`` 可清空加载器，便于测试和运行时切换。
        """

        self._factor_loader = loader

    @property
    def has_factor_loader(self) -> bool:
        """是否已配置引擎级因子加载器。"""

        return self._factor_loader is not None

    @staticmethod
    def _invoke_factor_loader(
        loader: Any,
        source: str,
        factor_name: str | None,
        kwargs: dict[str, Any],
    ) -> Any:
        """调用不同年代/来源的 loader，并保持错误原样向上传递。"""

        load_factor = getattr(loader, "load_factor", None)
        if callable(load_factor):
            call_kwargs = dict(kwargs)
            call_kwargs["source"] = source
            if factor_name is not None:
                call_kwargs["factor_name"] = factor_name
            return load_factor(**call_kwargs)

        if callable(loader):
            call_kwargs = dict(kwargs)
            call_kwargs["source"] = source
            if factor_name is not None:
                call_kwargs["factor_name"] = factor_name
            return loader(**call_kwargs)

        # 兼容当前 FactorLoader.load(module_name) 文件加载接口。数据库/源码
        # loader 应实现上面的统一 load_factor 或 callable 契约。
        legacy_load = getattr(loader, "load", None)
        if callable(legacy_load) and source == "file":
            module_name = (
                kwargs.get("module_name")
                or kwargs.get("module")
                or factor_name
            )
            if not module_name:
                raise ValueError(
                    "file 因子加载需要 module_name（或 factor_name）"
                )
            return legacy_load(module_name)

        raise TypeError(
            "因子加载器必须提供 load_factor(...)、可调用接口，"
            "或兼容文件加载器的 load(module_name)"
        )

    def _register_loaded(self, loaded: Any, factor_name: str | None) -> Any:
        """把 loader 返回的因子、因子库或映射纳入当前注册表。"""

        if isinstance(loaded, BaseFactor):
            if factor_name is not None and loaded.name != factor_name:
                raise ValueError(
                    f"加载因子名称 {loaded.name!r} 与请求 {factor_name!r} 不一致"
                )
            self.register(loaded)
            return loaded

        if isinstance(loaded, FactorLibrary):
            factors = library_factors(loaded)
            for factor in factors.values():
                self.register(factor)
            if factor_name is not None:
                try:
                    return factors[factor_name]
                except KeyError as exc:
                    raise KeyError(
                        f"因子库 {type(loaded).__name__} 中未找到因子 {factor_name!r}"
                    ) from exc
            return loaded

        if isinstance(loaded, Mapping):
            factors = {}
            for name, factor in loaded.items():
                if not isinstance(factor, BaseFactor):
                    raise TypeError(
                        f"因子加载器返回的 {name!r} 不是 BaseFactor，"
                        f"而是 {type(factor).__name__}"
                    )
                self.register(factor)
                factors[str(name)] = factor
            if factor_name is not None:
                factor = factors.get(factor_name)
                if factor is None:
                    factor = next(
                        (item for item in factors.values() if item.name == factor_name),
                        None,
                    )
                if factor is None:
                    raise KeyError(f"加载结果中未找到因子 {factor_name!r}")
                if factor.name != factor_name:
                    raise ValueError(
                        f"加载因子名称 {factor.name!r} 与请求 {factor_name!r} 不一致"
                    )
                return factor
            if len(factors) == 1:
                return next(iter(factors.values()))
            return factors

        raise TypeError(
            "因子加载器必须返回 BaseFactor、FactorLibrary 或"
            " {name: BaseFactor} 映射"
        )

    def factor_loader(
        self,
        source: str = "database",
        *,
        factor_name: str | None = None,
        loader: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """从指定来源加载因子并注册。

        ``source`` 只作为路由信息传给 loader；内置因子默认使用数据库，
        自定义源码仍通过 ``code`` 路径解析。单次调用可用 ``loader=`` 覆盖
        引擎级 loader，便于测试或切换来源实现。
        """

        active_loader = loader if loader is not None else self._factor_loader
        if active_loader is None:
            raise RuntimeError(
                "FactorEngine 尚未设置因子加载器，请先传入 factor_loader 或调用 "
                "set_factor_loader(...)"
            )
        normalized_source = str(source).strip().lower()
        if not normalized_source:
            raise ValueError("因子加载 source 不能为空")
        loaded = self._invoke_factor_loader(
            active_loader,
            normalized_source,
            factor_name,
            kwargs,
        )
        return self._register_loaded(loaded, factor_name)

    def load_factor(
        self,
        source: str = "database",
        *,
        factor_name: str | None = None,
        loader: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """``factor_loader`` 的语义化别名，供业务层调用。"""

        return self.factor_loader(
            source,
            factor_name=factor_name,
            loader=loader,
            **kwargs,
        )

    def _resolve_factor(self, spec: FactorBacktestSpec) -> None:
        """根据回测规格加载或生成当前任务私有的因子对象。

        因子名称、因子库和用户源码都属于因子解析职责。BacktestEngine
        只把已经确定有效截止日的规格交给这里，不参与来源判断或加载。
        """

        if not isinstance(spec, FactorBacktestSpec):
            raise FactorBacktestParameterError(
                "FactorEngine._resolve_factor 只接受 FactorBacktestSpec"
            )

        registered = self.factors.get(spec.factor_name)
        if registered is not None:
            self._factor = registered
            return

        self._factor = None

        source = "code" if spec.factor_code is not None else "database"
        try:
            active_loader = self._factor_loader
            if active_loader is None:
                # 默认加载器属于因子服务层。采用惰性导入，避免把源码加载
                # 和内置资产索引在普通 FactorEngine 计算时提前初始化。
                from app.services.factor.loader import load_factor_from_spec

                active_loader = load_factor_from_spec
            loaded = self.load_factor(
                source=source,
                factor_name=spec.factor_name,
                loader=active_loader,
                factor_code=spec.factor_code,
                library_names=spec.library_names,
                spec=spec,
            )
        except FactorBacktestParameterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FactorBacktestParameterError(str(exc)) from exc

        if not isinstance(loaded, BaseFactor):
            raise FactorBacktestParameterError(
                f"因子 loader 未返回 {spec.factor_name!r} 对应的 BaseFactor"
            )
        self._factor = loaded

    def compute_from_spec(
        self,
        spec: FactorBacktestSpec,
        panel: Panel,
    ) -> pd.DataFrame:
        """按回测规格私有解析因子并计算因子面板。

        ``BacktestEngine`` 只传递请求规格和数据面板；原始 ``BaseFactor``
        不跨越这一边界，也不会写入 ``FactorBacktestSpec``。
        """

        self._resolve_factor(spec)
        if self._factor is None:  # pragma: no cover - resolver contract
            raise FactorBacktestParameterError("FactorEngine 未解析出因子")
        values = self.backend.execute(self._factor.compute, panel)
        return _normalize_factor_output(self._factor, values)

    def factor_metadata(self) -> dict[str, str]:
        """返回当前已解析因子的展示元信息，不暴露运行期因子对象。"""

        if self._factor is None:
            raise FactorBacktestParameterError("FactorEngine 尚未解析因子")
        return {"name": self._factor.name, "author": self._factor.author}

    def register(self, factor: BaseFactor) -> None:
        """注册因子。"""
        if not isinstance(factor, BaseFactor):
            raise TypeError(
                f"只能注册 BaseFactor 子类，得到 {type(factor).__name__}"
            )
        self.factors[factor.name] = factor

    def _get_factor(self, factor_name: str) -> BaseFactor:
        """统一解析已注册因子，保证各计算入口错误一致。"""

        try:
            return self.factors[factor_name]
        except KeyError as exc:
            raise KeyError(
                f"未注册因子 {factor_name!r}，已注册: {list(self.factors)}"
            ) from exc

    def _compute_registered(self, factor_name: str, panel: Panel) -> pd.DataFrame:
        """在面板上执行已注册因子，并统一结果形状。"""

        factor = self._get_factor(factor_name)
        values = self.backend.execute(factor.compute, panel)
        return _normalize_factor_output(factor, values)

    def _panels_for(
        self, data_provider, universe: Universe,
        start: Optional[str], end: Optional[str],
        fields: Optional[Sequence[str]],
    ) -> Panel:
        panels = data_provider.get_panels(start, end, fields)
        # 按 universe 过滤列（懒执行：仅因子访问到的字段才真正读盘+过滤）
        symbols = resolve_universe(
            data_provider, universe, as_of=first_panel_date(panels)
        )
        return Panel(
            panels,
            symbols=symbols,
            index_loader=lambda name: data_provider.get_index(name, start, end),
        )

    def compute_panel(self, factor_name: str, panel: Panel) -> pd.DataFrame:
        """在已构建好的 ``Panel`` 上计算单个因子，返回 ``日期×标的`` 宽表。

        供调用方复用已取回的面板，避免重复 ``get_panels`` 取数。
        """
        return self._compute_registered(factor_name, panel)

    def preprocess(
        self,
        factor_values: pd.DataFrame,
        *,
        eligibility_mask: pd.DataFrame | None = None,
        winsorize: int = 0,
        standardize: int = 0,
    ) -> pd.DataFrame:
        """应用研究样本掩码及可选的截面因子预处理。

        掩码先于去极值和标准化应用，保证无效股票不会参与截面参数估计。
        输入始终复制，调用不会改变因子计算结果或共享行情状态。
        """

        if eligibility_mask is not None:
            eligible = eligibility_mask.reindex(
                index=factor_values.index, columns=factor_values.columns
            ).fillna(False).astype(bool)
            values = factor_values.mask(~eligible)
        else:
            values = factor_values
        if winsorize == 0 and standardize == 0:
            return values
        return preprocess_factor_values(
            values,
            winsorize=int(winsorize),
            standardize=int(standardize),
        )

    def compute(
        self,
        factor_name: str | None = None,
        data_provider=None,
        universe: Universe | None = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """计算本次回测因子，或兼容计算已注册因子。"""
        if factor_name is None:
            return self._compute_factor_value()
        self._get_factor(factor_name)
        if data_provider is None or universe is None:
            raise TypeError("通用因子计算需要 factor_name、data_provider 和 universe")
        panel = self._panels_for(data_provider, universe, start, end, fields)
        return self.compute_panel(factor_name, panel)

    def compute_all(
        self,
        data_provider,
        universe: Universe,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """计算所有已注册因子，返回 ``{因子名: 宽表}``。面板只取一次复用。"""
        panel = self._panels_for(data_provider, universe, start, end, fields)
        return {
            name: self._compute_registered(name, panel)
            for name in self.factors
        }
