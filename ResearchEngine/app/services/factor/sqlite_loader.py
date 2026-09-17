"""SQLite 因子库的只读仓库与运行时加载器。

新的因子库把目录信息和单因子源码放在 SQLite 中，把公共算子放在一个独立的
``tool.py`` 中。本模块只负责两件事：读取数据库记录，以及把记录中的一个顶层
函数编译成现有 :class:`BaseFactor` 契约。回测引擎仍然只接触 ``BaseFactor``，不
感知 SQLite、源码字符串或外部工具文件。

源码编译前会执行版本化的最小兼容归一化，以兼容数据库静态化时留下的局部变量
引用和 pandas rolling 回调写法；归一化版本也会参与因子执行指纹。

数据库和工具文件默认位于项目 ``app/assets/factors`` 目录，也可以分别通过
``SVQUANT_FACTOR_DB_PATH``/``SVQUANT_FACTOR_DB`` 和
``SVQUANT_FACTOR_TOOL_PATH``/``SVQUANT_FACTOR_TOOL`` 覆盖。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import importlib.util
import inspect
from pathlib import Path
import sqlite3
from types import ModuleType
from typing import Any, Iterable
from urllib.parse import quote

import numpy as np
import pandas as pd

from app.services.factor.base import BaseFactor, FactorLibrary, library_factors
from app.utils.paths import factor_database_path, factor_tool_path


_FACTOR_CODE_ADAPTER_VERSION = "sqlite-factor-code-adapter-v1"


class FactorDatabaseError(RuntimeError):
    """因子数据库或数据库源码不符合运行时契约。"""


@dataclass(frozen=True)
class FactorLibraryRecord:
    """SQLite ``factor_libraries`` 表中的库记录。"""

    library_id: int
    library_name: str
    description: str | None
    factor_count: int


@dataclass(frozen=True)
class FactorRecord:
    """SQLite ``factors`` 与 ``categories`` 联表后的因子记录。"""

    sv_id: str
    library_id: int
    library_name: str
    factor_name: str
    factor_name_en: str
    factor_code: str
    category_id: str
    category_name: str | None
    description: str | None
    function_name: str


class _SQLiteFactorLibraryMixin:
    """SQLite 源码所需的少量数据对象兼容属性。

    新 ``tool.py`` 已收编公共算子；这里仅处理数据库中仍以数据对象属性形式
    表达的兼容字段/指标，不把它们暴露成额外的可登记因子方法。
    """

    _PANEL_FIELD_NAMES = frozenset(
        {
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "turnover",
            "current_mv",
            "dividend_yield_ttm",
            "pe_ttm",
            "pb_mrq",
            "pcf_operating_cash_flow_ttm",
            "listed_status",
            "the_sw_industry_code",
            "up_and_down_status",
            "ps_ttm",
        }
    )

    def __getattribute__(self, name: str):
        """让面板字段优先于同名数据库因子方法。

        数据库中存在名为 ``volume``、``amount`` 等因子，而这些名字也是
        ``FactorLibrary`` 的面板属性。因子方法内部的 ``self.volume`` 仍应
        表示行情字段；仅在面板已经绑定时覆盖同名方法，未绑定时保留方法
        发现/注册所需的正常属性查找。
        """

        if name in _SQLiteFactorLibraryMixin._PANEL_FIELD_NAMES:
            panel = object.__getattribute__(self, "_panel")
            if panel is not None:
                return panel[name]
        return super().__getattribute__(name)

    @property
    def industry(self):
        if self._panel is None:
            raise AttributeError("industry")
        return self._panel["the_sw_industry_code"]

    @property
    def subindustry(self):
        if self._panel is None:
            raise AttributeError("subindustry")
        return self._panel["the_sw_industry_code"]

    @property
    def sector(self):
        if self._panel is None:
            raise AttributeError("sector")
        return self._panel["the_sw_industry_code"]

    @property
    def ps_ttm(self):
        if self._panel is None:
            raise AttributeError("ps_ttm")
        return self._panel["ps_ttm"]

    def __getattr__(self, name: str):
        if name == "bbi":
            return self._compat_bbi
        if name == "rsi_14":
            return self._compat_rsi_14
        if name == "atr_percent":
            return self._compat_atr_percent
        raise AttributeError(name)

    def _compat_bbi(
        self,
        short1: int = 3,
        short2: int = 6,
        long1: int = 12,
        long2: int = 24,
    ):
        return sum(
            self.close.rolling(window).mean()
            for window in (short1, short2, long1, long2)
        ) / 4.0

    def _compat_rsi_14(self, window: int = 14):
        delta = self.close.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = -delta.clip(upper=0).rolling(window).mean()
        relative_strength = gain / (loss + 1e-10)
        return 100.0 - 100.0 / (1.0 + relative_strength)

    def _compat_atr_percent(self, window: int = 14):
        previous_close = self.close.shift(1)
        true_range = np.maximum(
            np.maximum(self.high - self.low, (self.high - previous_close).abs()),
            (self.low - previous_close).abs(),
        )
        atr = true_range.rolling(window).mean()
        price = self.close.abs()
        return atr / price.where(price > 1e-10)


def _readonly_uri(path: Path) -> str:
    """构造 SQLite 只读 URI，避免加载器意外修改用户的因子库。"""

    return f"file:{quote(str(path.resolve()), safe='/:')}?mode=ro"


def _parse_function_name(code: str, *, source_name: str) -> str:
    """校验源码并返回唯一的顶层函数名。"""

    if not isinstance(code, str) or not code.strip():
        raise FactorDatabaseError(f"因子 {source_name!r} 的 factor_code 为空")
    try:
        tree = ast.parse(code, filename=source_name, mode="exec")
    except SyntaxError as exc:
        raise FactorDatabaseError(f"因子 {source_name!r} 源码语法错误: {exc}") from exc

    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1:
        raise FactorDatabaseError(
            f"因子 {source_name!r} 必须恰有一个顶层 def，实际为 {len(functions)} 个"
        )
    if any(isinstance(node, ast.AsyncFunctionDef) for node in tree.body):
        raise FactorDatabaseError(f"因子 {source_name!r} 不支持 async def")
    return functions[0].name


class _StaticizedFactorCodeAdapter(ast.NodeTransformer):
    """修正新库静态化过程中保留下来的、可确定等价的调用写法。

    当前数据库源码有少量代码把函数内已经计算出的 ``vwap``/``true_range``
    写成了 ``tool.vwap``/``tool.true_range``，以及把需要 Series 的滚动回调
    写成 ``raw=True``。只在局部变量明确存在且回调确实使用 ``iloc`` 或
    ``quantile`` 时修正，避免改变正常的公共算子调用。
    """

    _LOCAL_SERIES_NAMES = frozenset({"vwap", "true_range"})

    def __init__(self) -> None:
        self.local_names: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.local_names.update(
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
        )
        node.body = [self.visit(child) for child in node.body]
        return node

    def visit_Attribute(self, node: ast.Attribute):
        visited = self.generic_visit(node)
        if not isinstance(visited, ast.Attribute):
            return visited
        node = visited
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "tool"
            and node.attr in self._LOCAL_SERIES_NAMES
            and node.attr in self.local_names
        ):
            return ast.copy_location(ast.Name(id=node.attr, ctx=ast.Load()), node)
        return node

    def visit_Call(self, node: ast.Call):
        visited = self.generic_visit(node)
        if not isinstance(visited, ast.Call):
            return visited
        node = visited
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "tool"
            and node.func.attr == "_safe_divide"
        ):
            for keyword in node.keywords:
                if keyword.arg == "epsilon":
                    keyword.arg = "eps"

        if isinstance(node.func, ast.Attribute) and node.func.attr == "apply":
            callback_uses_series_api = any(
                isinstance(child, ast.Lambda)
                and any(
                    isinstance(descendant, ast.Attribute)
                    and descendant.attr in {"iloc", "quantile"}
                    for descendant in ast.walk(child)
                )
                for child in ast.walk(node)
            )
            if callback_uses_series_api:
                for keyword in node.keywords:
                    if keyword.arg == "raw" and isinstance(keyword.value, ast.Constant):
                        if keyword.value.value is True:
                            keyword.value = ast.Constant(False)
        return node


def _adapt_factor_code(code: str, *, source_name: str) -> ast.Module:
    """解析并归一化 SQLite 因子源码，返回可编译 AST。"""

    try:
        tree = ast.parse(code, filename=source_name, mode="exec")
    except SyntaxError as exc:
        raise FactorDatabaseError(f"因子 {source_name!r} 源码语法错误: {exc}") from exc
    tree = _StaticizedFactorCodeAdapter().visit(tree)
    ast.fix_missing_locations(tree)
    return tree


def _library_label(value: str | int | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class SQLiteFactorRepository:
    """因子 SQLite 的只读访问层。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.path = Path(db_path or factor_database_path()).expanduser().resolve()

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(f"因子数据库不存在: {self.path}")
        try:
            connection = sqlite3.connect(_readonly_uri(self.path), uri=True)
        except sqlite3.Error as exc:
            raise FactorDatabaseError(f"无法打开因子数据库 {self.path}: {exc}") from exc
        connection.row_factory = sqlite3.Row
        return connection

    def _library(self, library_name: str | int | None = None) -> FactorLibraryRecord:
        label = _library_label(library_name)
        with self._connect() as connection:
            if label is None:
                rows = connection.execute(
                    """
                    SELECT l.library_id, l.library_name, l.description,
                           COUNT(f.sv_id) AS factor_count
                    FROM factor_libraries AS l
                    LEFT JOIN factors AS f ON f.library_id = l.library_id
                    GROUP BY l.library_id, l.library_name, l.description
                    ORDER BY l.library_id
                    """
                ).fetchall()
                if len(rows) != 1:
                    raise ValueError(
                        "未指定因子库且数据库不是单库结构；请提供 library_name"
                    )
                row = rows[0]
            else:
                row = connection.execute(
                    """
                    SELECT l.library_id, l.library_name, l.description,
                           COUNT(f.sv_id) AS factor_count
                    FROM factor_libraries AS l
                    LEFT JOIN factors AS f ON f.library_id = l.library_id
                    WHERE l.library_name = ? OR CAST(l.library_id AS TEXT) = ?
                    GROUP BY l.library_id, l.library_name, l.description
                    """,
                    (label, label),
                ).fetchone()
                if row is None:
                    raise KeyError(f"未找到 SQLite 因子库: {library_name}")
        return FactorLibraryRecord(
            library_id=int(row["library_id"]),
            library_name=str(row["library_name"]),
            description=row["description"],
            factor_count=int(row["factor_count"]),
        )

    def get_library(
        self,
        library_name: str | int | None = None,
    ) -> FactorLibraryRecord:
        """解析库名或库 ID，并返回规范化库记录。"""

        return self._library(library_name)

    def has_library(self, library_name: str | int) -> bool:
        try:
            self._library(library_name)
        except (KeyError, FileNotFoundError, FactorDatabaseError, sqlite3.Error):
            return False
        return True

    def list_libraries(self) -> list[FactorLibraryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT l.library_id, l.library_name, l.description,
                       COUNT(f.sv_id) AS factor_count
                FROM factor_libraries AS l
                LEFT JOIN factors AS f ON f.library_id = l.library_id
                GROUP BY l.library_id, l.library_name, l.description
                ORDER BY l.library_id
                """
            ).fetchall()
        return [
            FactorLibraryRecord(
                library_id=int(row["library_id"]),
                library_name=str(row["library_name"]),
                description=row["description"],
                factor_count=int(row["factor_count"]),
            )
            for row in rows
        ]

    def list_factors(
        self,
        library_name: str | int | None = None,
        *,
        validate_code: bool = True,
    ) -> list[FactorRecord]:
        library = self._library(library_name)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT f.sv_id, f.library_id, l.library_name,
                       f.factor_name, f.factor_name_en, f.factor_code,
                       f.category_id, c.category_name, f.description
                FROM factors AS f
                JOIN factor_libraries AS l ON l.library_id = f.library_id
                LEFT JOIN categories AS c ON c.category_id = f.category_id
                WHERE f.library_id = ?
                ORDER BY f.sv_id
                """,
                (library.library_id,),
            ).fetchall()
        records: list[FactorRecord] = []
        for row in rows:
            code = str(row["factor_code"])
            function_name = _parse_function_name(
                code,
                source_name=f"{self.path}#{row['sv_id']}",
            ) if validate_code else ""
            records.append(
                FactorRecord(
                    sv_id=str(row["sv_id"]),
                    library_id=int(row["library_id"]),
                    library_name=str(row["library_name"]),
                    factor_name=str(row["factor_name"]),
                    factor_name_en=str(row["factor_name_en"]),
                    factor_code=code,
                    category_id=str(row["category_id"]),
                    category_name=(
                        str(row["category_name"])
                        if row["category_name"] is not None
                        else None
                    ),
                    description=(
                        str(row["description"])
                        if row["description"] is not None
                        else None
                    ),
                    function_name=function_name,
                )
            )
        return records

    def get_factor(
        self,
        factor_name: str,
        *,
        library_name: str | int | None = None,
    ) -> FactorRecord:
        """按稳定 ID、中文名、英文名或源码函数名查找因子。"""

        requested = str(factor_name).strip()
        if not requested:
            raise ValueError("factor_name 不能为空")
        library = self._library(library_name)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT f.sv_id, f.library_id, l.library_name,
                       f.factor_name, f.factor_name_en, f.factor_code,
                       f.category_id, c.category_name, f.description
                FROM factors AS f
                JOIN factor_libraries AS l ON l.library_id = f.library_id
                LEFT JOIN categories AS c ON c.category_id = f.category_id
                WHERE f.library_id = ?
                  AND (f.sv_id = ? OR f.factor_name = ? OR f.factor_name_en = ?)
                """,
                (library.library_id, requested, requested, requested),
            ).fetchone()

        if row is None:
            candidates = [
                record
                for record in self.list_factors(library.library_name)
                if record.function_name == requested
            ]
            if not candidates:
                raise KeyError(
                    f"未找到因子 {factor_name!r}（因子库: {library.library_name!r}）"
                )
            if len(candidates) > 1:
                raise ValueError(
                    f"因子函数名 {factor_name!r} 在库 {library.library_name!r} 中不唯一"
                )
            return candidates[0]

        code = str(row["factor_code"])
        return FactorRecord(
            sv_id=str(row["sv_id"]),
            library_id=int(row["library_id"]),
            library_name=str(row["library_name"]),
            factor_name=str(row["factor_name"]),
            factor_name_en=str(row["factor_name_en"]),
            factor_code=code,
            category_id=str(row["category_id"]),
            category_name=(
                str(row["category_name"])
                if row["category_name"] is not None
                else None
            ),
            description=(
                str(row["description"])
                if row["description"] is not None
                else None
            ),
            function_name=_parse_function_name(
                code,
                source_name=f"{self.path}#{row['sv_id']}",
            ),
        )

    def source_hash(
        self,
        record: FactorRecord,
        *,
        tool_path: str | Path | None = None,
    ) -> str:
        """生成包含因子源码和公共工具源码的稳定执行指纹。"""

        tool_bytes = Path(tool_path or factor_tool_path()).expanduser().resolve().read_bytes()
        payload = (
            record.sv_id.encode("utf-8")
            + b"\0"
            + _FACTOR_CODE_ADAPTER_VERSION.encode("ascii")
            + b"\0"
            + record.factor_code.encode("utf-8")
            + b"\0"
            + tool_bytes
        )
        return hashlib.sha256(payload).hexdigest()

    def catalog_signature(self, *, tool_path: str | Path | None = None) -> str:
        """生成数据库与公共工具的整体版本指纹，用于批量目录版本。"""

        db_bytes = self.path.read_bytes()
        tool_bytes = Path(tool_path or factor_tool_path()).expanduser().resolve().read_bytes()
        return hashlib.sha256(
            _FACTOR_CODE_ADAPTER_VERSION.encode("ascii")
            + b"\0"
            + db_bytes
            + b"\0"
            + tool_bytes
        ).hexdigest()


@lru_cache(maxsize=16)
def _load_tool_module_cached(
    path_text: str,
    mtime_ns: int,
    size: int,
) -> ModuleType:
    """按文件指纹缓存外部 ``tool.py`` 模块。"""

    path = Path(path_text)
    module_name = f"svquant_factor_tool_{hashlib.sha256(path_text.encode()).hexdigest()[:16]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载因子公共工具模块: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_factor_tool(tool_path: str | Path | None = None) -> ModuleType:
    """加载用户指定的公共因子工具模块。"""

    path = Path(tool_path or factor_tool_path()).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"因子公共工具文件不存在: {path}")
    stat = path.stat()
    return _load_tool_module_cached(str(path), stat.st_mtime_ns, stat.st_size)


class SQLiteFactorLoader:
    """把 SQLite 因子记录编译为现有 ``BaseFactor``。"""

    def __init__(
        self,
        db_path: str | Path | None = None,
        tool_path: str | Path | None = None,
        *,
        repository: SQLiteFactorRepository | None = None,
    ) -> None:
        if repository is not None and db_path is not None:
            raise ValueError("repository 与 db_path 不能同时指定")
        self.repository = repository or SQLiteFactorRepository(db_path)
        self.tool_path = Path(tool_path or factor_tool_path()).expanduser().resolve()
        self._tool: ModuleType | None = None

    def _tool_module(self) -> ModuleType:
        if self._tool is None:
            self._tool = load_factor_tool(self.tool_path)
        return self._tool

    def _compile_function(self, record: FactorRecord):
        source_name = f"{self.repository.path}#{record.sv_id}"
        namespace: dict[str, Any] = {
            "__name__": f"svquant.sqlite_factor.{record.sv_id}",
            "__file__": source_name,
            "np": np,
            "pd": pd,
            "tool": self._tool_module(),
        }
        try:
            exec(
                compile(
                    _adapt_factor_code(record.factor_code, source_name=source_name),
                    source_name,
                    "exec",
                ),
                namespace,
                namespace,
            )
        except Exception as exc:  # noqa: BLE001 - 附加数据库因子上下文
            raise FactorDatabaseError(
                f"因子 {record.sv_id} ({record.factor_name}) 编译失败: {exc}"
            ) from exc
        function = namespace.get(record.function_name)
        if not inspect.isfunction(function):
            raise FactorDatabaseError(
                f"因子 {record.sv_id} 未生成函数 {record.function_name!r}"
            )
        return function

    def load_library(
        self,
        library_name: str | int | None = None,
    ) -> FactorLibrary:
        records = self.repository.list_factors(library_name)
        if not records:
            raise ValueError(f"因子库 {library_name!r} 没有因子")
        methods: dict[str, Any] = {}
        for record in records:
            if record.function_name in methods:
                raise FactorDatabaseError(
                    f"因子库 {record.library_name!r} 存在重复函数名: {record.function_name}"
                )
            methods[record.function_name] = self._compile_function(record)
        class_name = "SQLiteFactorLibrary_" + str(records[0].library_id)
        library_type = type(
            class_name,
            (_SQLiteFactorLibraryMixin, FactorLibrary),
            {
                "__module__": __name__,
                "author": records[0].library_name,
                **methods,
            },
        )
        return library_type()

    def load_factor(
        self,
        source: str = "database",
        *,
        factor_name: str | None = None,
        library_name: str | int | None = None,
        library_names: Iterable[str] | None = None,
        **_kwargs: Any,
    ) -> BaseFactor:
        del source  # 统一 loader 契约中的路由字段，SQLite loader 不需要分支。
        if isinstance(library_names, str):
            names = [library_names]
        else:
            names = list(library_names or [])
        if library_name is not None:
            names.append(str(library_name))
        if len(set(names)) > 1:
            raise ValueError("SQLite 内置因子只能指定一个因子库")
        if factor_name is None:
            raise ValueError("加载 SQLite 因子必须提供 factor_name")
        selected_library = names[0] if names else None
        record = self.repository.get_factor(
            factor_name,
            library_name=selected_library,
        )
        function = self._compile_function(record)
        library_type = type(
            f"SQLiteFactorLibrary_{record.sv_id}",
            (_SQLiteFactorLibraryMixin, FactorLibrary),
            {
                "__module__": __name__,
                "author": record.library_name,
                record.function_name: function,
            },
        )
        library = library_type()
        factor = library_factors(library)[record.function_name]
        # ``factor_name`` 是请求的外部键；用它命名可让 FactorEngine 的严格名称
        # 校验同时支持 sv_id、中文名、英文名和源码函数名。
        factor.name = str(factor_name).strip() or record.sv_id
        factor.db_record = record
        factor.factor_source_hash = self.repository.source_hash(
            record,
            tool_path=self.tool_path,
        )
        return factor

    def load_all(
        self,
        library_name: str | int | None = None,
    ) -> dict[str, BaseFactor]:
        library = self.load_library(library_name)
        factors = library_factors(library)
        records = self.repository.list_factors(library_name)
        by_function = {record.function_name: record for record in records}
        result: dict[str, BaseFactor] = {}
        for function_name, factor in factors.items():
            record = by_function[function_name]
            factor.name = record.sv_id
            factor.db_record = record
            factor.factor_source_hash = self.repository.source_hash(
                record,
                tool_path=self.tool_path,
            )
            result[record.sv_id] = factor
        return result


def database_factor_library_names(
    db_path: str | Path | None = None,
) -> tuple[str, ...]:
    return tuple(record.library_name for record in SQLiteFactorRepository(db_path).list_libraries())


def load_factor_from_database(
    factor_name: str,
    *,
    library_name: str | int | None = None,
    db_path: str | Path | None = None,
    tool_path: str | Path | None = None,
) -> BaseFactor:
    return SQLiteFactorLoader(db_path=db_path, tool_path=tool_path).load_factor(
        factor_name=factor_name,
        library_name=library_name,
    )


__all__ = [
    "FactorDatabaseError",
    "FactorLibraryRecord",
    "FactorRecord",
    "SQLiteFactorRepository",
    "SQLiteFactorLoader",
    "database_factor_library_names",
    "load_factor_from_database",
    "load_factor_tool",
]
