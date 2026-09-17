"""``DataEngine`` - 应用级市场数据快照与统一读取引擎。

依据 ``docs/99-历史归档/FEAT-001-QuantCore基础能力/04-class-design.md`` DataEngine 节：

    属性：
      provider: IDataProvider    -- 当前已加载 release 的底层来源

    方法：
      set_provider(provider: IDataProvider)
      get_bars(symbol, start, end, fields) -> DataFrame
      get_universe(date) -> List[str]

FastAPI 进程在启动期创建唯一的 DataEngine 并加载活动 release；Experiment
只从它读取共享只读数据或取得任务私有切片。DataEngine 不属于
ExperimentManager，Manager 只负责调度。
"""

from __future__ import annotations

from collections.abc import Mapping
import inspect
import os
import threading
from pathlib import Path
from typing import Any, List, Optional, Sequence, TypeVar

import pandas as pd

from app.database.data.interface import IDataProvider
from app.database.data.field_cache import FieldFrameCache


_T = TypeVar("_T")
_CORE_PROVIDER_METHODS = (
    "get_bars",
    "get_universe",
    "get_symbols",
)


def _limit_up_status(values: pd.Series) -> pd.Series:
    """从 iFinD 涨跌停原始文本提取涨停状态，排除否定状态。"""

    matches = values.str.contains(
        "涨停|limit.?up|up.?limit",
        case=False,
        regex=True,
        na=False,
    )
    negative = values.str.contains(
        r"(?:非|未|not\s*)(?:涨跌停|涨停|limit.?up|up.?limit)",
        case=False,
        regex=True,
        na=False,
    )
    return matches & ~negative


def default_market_data_dir() -> Path:
    """返回应用默认的 ``marketdata`` 根目录。"""

    repo_root = Path(__file__).resolve().parents[4]
    return Path(os.environ.get("SVQUANT_DATA_DIR", repo_root / "marketdata"))


class DataEngine:
    """统一数据读取入口。

    上层（app）只与本类交互，不接触任何具体数据源实现。
    切换数据源只需调用 :meth:`set_provider`。
    """

    def __init__(self, provider: Optional[IDataProvider] = None) -> None:
        self.provider: Optional[IDataProvider] = None
        self._cache: FieldFrameCache | None = None
        self._closed = False
        if provider is not None:
            self.load(provider)

    @classmethod
    def get_instance(cls) -> "DataEngine":
        """返回本 ResearchEngine 进程唯一的 DataEngine。"""

        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def configure_instance(cls, instance: "DataEngine") -> "DataEngine":
        """由应用启动装配全局实例；测试可注入隔离实例。"""

        with cls._instance_lock:
            cls._instance = instance
        return instance

    @staticmethod
    def _validate_provider(provider: Any) -> None:
        """在切换数据源时尽早检查核心读取契约。

        这里使用结构化检查而不是强制 ``isinstance(IDataProvider)``，既能
        拦截误传的普通对象，也保留测试替身和外部 provider 的鸭子类型兼容性。
        ``get_panels``、``get_index`` 与 ``get_universe_at`` 属于可选能力，
        分别在调用时使用默认实现或给出 provider 的明确错误/回退行为。
        """

        missing = [
            name
            for name in _CORE_PROVIDER_METHODS
            if not callable(getattr(provider, name, None))
        ]
        if missing:
            raise TypeError(
                "provider 不满足 IDataProvider 读取契约，缺少方法: "
                f"{missing}"
            )

    def load(self, provider: IDataProvider) -> None:
        """加载一个数据 release，成为本 DataEngine 的唯一读取来源。

        DataEngine 只保存数据来源；字段由任务按时间范围读取，不做全量预热。
        """
        if self._closed:
            raise RuntimeError("DataEngine 已关闭")
        if provider is None:
            self.provider = None
            return
        self._validate_provider(provider)
        self.provider = provider
    def load_parquet(
        self,
        data_dir: str | Path,
    ) -> None:
        """从 MarketData Parquet 加载当前 release。

        字段缓存是 DataEngine 私有状态，不再由 provider 或 Manager 取得
        进程全局缓存。
        """
        from app.database.data.providers.field_parquet_provider import FieldParquetProvider

        self._cache = FieldFrameCache()
        self.load(FieldParquetProvider(data_dir, cache=self._cache))

    # ``set_provider`` 是已有低层使用方的同义入口；新代码应使用 ``load``，
    # 以强调这是一次 release 装载而非任务期间的任意切换。
    def set_provider(self, provider: IDataProvider) -> None:
        self.load(provider)

    def _require_provider(self) -> IDataProvider:
        if self._closed:
            raise RuntimeError("DataEngine 已关闭")
        if self.provider is None:
            raise RuntimeError(
                "DataEngine 尚未设置数据源，请先调用 set_provider(...)。"
            )
        return self.provider

    def _call(self, method: str, *args: Any, **kwargs: Any) -> _T:
        """统一调用 provider，避免各公开方法重复实现委托和契约检查。"""

        provider = self._require_provider()
        operation = getattr(provider, method, None)
        if operation is None and method == "get_panels":
            # 允许只实现逐标的核心契约的轻量 provider 复用
            # IDataProvider 的默认宽表拼装逻辑。
            return IDataProvider.get_panels(provider, *args, **kwargs)  # type: ignore[arg-type]
        if not callable(operation):
            raise TypeError(
                f"当前 provider {type(provider).__name__} 未实现 {method}(...)"
            )
        return operation(*args, **kwargs)

    @property
    def provider_name(self) -> str | None:
        """当前数据源名称，未配置 provider 时返回 ``None``。"""

        provider = self.provider
        if provider is None:
            return None
        return str(getattr(provider, "name", type(provider).__name__))

    @property
    def data_dir(self) -> Path | None:
        """当前 release 的物理目录；非文件型 provider 时可能不存在。"""

        value = getattr(self.provider, "data_dir", None)
        return Path(value).resolve() if value is not None else None

    @property
    def release_id(self) -> str | None:
        """当前已加载 release 的稳定身份。"""

        value = getattr(self.provider, "release_id", None)
        return str(value) if value is not None else None

    @property
    def data_engine(self) -> "DataEngine":
        """只读上下文消费方取得自身，不复制或创建新 Engine。"""

        return self

    def cache_stats(self) -> dict[str, int]:
        """返回本 DataEngine 私有字段缓存状态。"""

        if self._cache is not None:
            return self._cache.stats()
        stats = getattr(self.provider, "cache_stats", None)
        return stats() if callable(stats) else {}

    def close(self) -> None:
        """释放当前 release；应在所有 Experiment 停止后由应用调用。"""

        self.provider = None
        if self._cache is not None:
            self._cache.clear()
        self._closed = True

    def get_bars(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """读取单个标的行情，委托给当前 provider。"""
        return self._call("get_bars", symbol, start, end, fields)

    def get_universe(self, date: Optional[str] = None) -> List[str]:
        """获取股票池，委托给当前 provider。"""
        return self._call("get_universe", date)

    def get_universe_at(self, name: str, as_of: str | pd.Timestamp) -> List[str]:
        """获取指定时点的命名股票池；不支持历史快照时兼容旧 provider。"""
        provider = self._require_provider()
        resolver = getattr(provider, "get_universe_at", None)
        if callable(resolver):
            return resolver(name, as_of)
        return self._call("get_universe", name)

    def get_symbols(self) -> List[str]:
        """获取全部已知标的，委托给当前 provider。"""
        return self._call("get_symbols")

    def get_panels(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> Mapping[str, pd.DataFrame]:
        """获取多字段宽表面板，委托给当前 provider。"""
        return self._call("get_panels", start, end, fields)

    def get_task_panels(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
        symbols: Optional[Sequence[str]] = None,
    ) -> Mapping[str, pd.DataFrame]:
        """返回当前 Experiment 的私有行情面板。

        ``symbols`` 是可选的任务级列裁剪；宽表 provider 可以在读盘后再
        深拷贝指定列，从而避免先复制全市场再由 Panel 重切一次。
        """

        provider = self._require_provider()
        task_panels = getattr(provider, "get_task_panels", None)
        if callable(task_panels):
            if symbols is None:
                return task_panels(start, end, fields)
            # ``get_task_panels`` 是宽表 provider 的扩展能力，不属于旧版
            # IDataProvider 必选接口。旧 provider 可能仍只有三参数签名；在
            # 这种情况下保留它的任务隔离语义，让 Panel 在访问时再裁剪列。
            try:
                parameters = inspect.signature(task_panels).parameters.values()
            except (TypeError, ValueError):
                parameters = ()
            accepts_symbols = any(
                parameter.name == "symbols"
                or parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters
            )
            if accepts_symbols:
                return task_panels(start, end, fields, symbols=symbols)
            legacy_panels = task_panels(start, end, fields)
            if isinstance(legacy_panels, Mapping):
                requested = pd.Index(symbols)
                return {
                    name: frame.reindex(columns=requested).copy(deep=True)
                    for name, frame in legacy_panels.items()
                }
            return legacy_panels
        panels = self.get_panels(start, end, fields)
        requested = None if symbols is None else pd.Index(symbols)
        return {
            name: (
                frame.reindex(columns=requested).copy(deep=True)
                if requested is not None
                else frame.copy(deep=True)
            )
            for name, frame in panels.items()
        }

    def get_research_data(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        fields: Optional[Sequence[str]] = None,
    ):
        """返回按当前 MarketData 业务域建模的研究数据视图。

        此入口不改变 ``get_panels`` 的兼容契约。业务域对象中的 ``close``、
        ``pb_mrq``、``up_and_down_status`` 等字段仍是原生 DataFrame，可直接参与
        因子和策略的 Pandas 表达式。
        """

        from app.models.market_data import MarketDataRelease
        from app.services.data.panel import ResearchDataPanel

        provider = self._require_provider()
        release = MarketDataRelease.from_panels(
            self.get_panels(start, end, fields),
            data_version=getattr(provider, "data_version", None),
        )
        return ResearchDataPanel(release)

    def get_index(
        self,
        name: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取指数行情，委托给当前 provider。"""
        return self._call("get_index", name, start, end)

    def get_industry_map(self, data_dir: str | None = None) -> pd.Series | None:
        """读取可选股票行业映射。

        行业元数据不是行情面板，仍由 DataEngine 负责解析；找不到文件或
        缺少行业列时返回 ``None``，由 full 分析按可选能力降级。
        """

        from pathlib import Path

        root = Path(data_dir) if data_dir else getattr(self.provider, "data_dir", None)
        if root is None:
            return None
        root = Path(root)
        if (root / "current").is_dir():
            root = root / "current"
        path = root / "metadata" / "stock_info.parquet"
        if not path.exists():
            path = root / "stock_info.parquet"
        if not path.exists():
            return None
        try:
            frame = pd.read_parquet(path)
            if "industry" not in frame.columns:
                return None
            for column in ("code", "symbol", "ts_code"):
                if column in frame.columns:
                    return frame.set_index(column)["industry"]
            return frame["industry"]
        except (OSError, ValueError, KeyError):
            return None

    def build_filter_mask(
        self,
        panels: Mapping[str, pd.DataFrame] | Any,
        *,
        filter_suspended: bool = False,
        filter_limit_up: bool = False,
    ) -> dict[str, Any]:
        """根据可选行情状态构造因子研究有效池。

        返回普通映射 ``{"mask", "status", "warnings"}``，其中 mask 为
        ``True=允许进入研究样本``。该方法只读取状态，不删除行情行，也不
        修改传入面板；缺少可选状态字段时跳过对应过滤并留下可序列化告警。
        ``Panel`` 和 provider 返回的字段映射都可直接传入。
        """

        def has_field(name: str) -> bool:
            try:
                return name in panels
            except TypeError:
                return name in getattr(panels, "fields", ())

        def get_field(name: str) -> pd.DataFrame:
            try:
                return panels[name]
            except (KeyError, TypeError):
                return getattr(panels, name)

        reference = None
        if has_field("close"):
            reference = get_field("close")
        else:
            for name in getattr(panels, "fields", panels):
                if has_field(str(name)):
                    reference = get_field(str(name))
                    break
        if reference is None:
            raise ValueError("无法构造过滤掩码：面板没有可用字段")

        mask = pd.DataFrame(True, index=reference.index, columns=reference.columns)
        status: dict[str, str] = {}
        warnings: list[str] = []

        def apply_boolean_filter(option: str, field: str) -> None:
            nonlocal mask
            if not option:
                status[field] = "disabled"
                return
            if not has_field(field):
                status[field] = "skipped_missing_field"
                warnings.append(f"已跳过{field}过滤：当前数据版本缺少 {field} 状态字段")
                return
            values = get_field(field).reindex(index=mask.index, columns=mask.columns)
            missing = int(values.isna().sum().sum())
            if missing:
                warnings.append(
                    f"{field} 状态覆盖不足：{missing} 个值缺失，按放行处理"
                )
                status[field] = "enabled_partial"
            else:
                status[field] = "enabled"
            mask &= ~values.fillna(False).astype(bool)

        apply_boolean_filter(filter_suspended, "is_suspended")

        if not filter_limit_up:
            status["limit_up"] = "disabled"
        else:
            limit_values = None
            source = None
            if has_field("up_and_down_status"):
                raw_status = get_field("up_and_down_status").reindex(
                    index=mask.index, columns=mask.columns
                )
                # 把整张状态面板压成一个 Series，只执行一次字符串匹配；
                # ``DataFrame.apply`` 会为数千个标的重复进入 Python 调用层。
                status_values = raw_status.astype("string")
                flat_status = pd.Series(
                    status_values.to_numpy(dtype=object).reshape(-1),
                    dtype="string",
                )
                flat_limit = _limit_up_status(flat_status)
                limit_values = pd.DataFrame(
                    flat_limit.to_numpy(dtype=bool).reshape(raw_status.shape),
                    index=mask.index,
                    columns=mask.columns,
                )
                # 保留原始缺失状态，不能在字符串转换时把它们静默变成
                # False；缺失值按放行处理，但必须进入覆盖不足告警。
                limit_values = limit_values.mask(raw_status.isna())
                source = "up_and_down_status"
            if limit_values is None:
                status["limit_up"] = "skipped_missing_field"
                warnings.append(
                    "已跳过涨停过滤：当前数据版本缺少 up_and_down_status 状态字段"
                )
            else:
                limit_values = limit_values.reindex(
                    index=mask.index, columns=mask.columns
                )
                missing = int(limit_values.isna().sum().sum())
                if missing:
                    status["limit_up"] = "enabled_partial"
                    warnings.append(
                        f"{source} 状态覆盖不足：{missing} 个值缺失，按放行处理"
                    )
                else:
                    status["limit_up"] = "enabled"
                mask &= ~limit_values.fillna(False).astype(bool)

        return {"mask": mask, "status": status, "warnings": warnings}

    _instance: "DataEngine | None" = None
    _instance_lock = threading.RLock()
