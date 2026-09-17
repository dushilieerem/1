"""因子加载门面与迁移期文件加载器。

依据 ``ResearchEngine/docs/03-功能文档/FEAT-002-研究引擎/04-class-design.md`` FactorLoader 节：

    属性：
      factor_dir: str
      factors: Dict[str, BaseFactor]

    方法：
      load(module_name: str) -> BaseFactor
      load_all() -> Dict[str, BaseFactor]
      register(name: str, factor: BaseFactor)

默认的内置因子解析由 ``load_factor_from_spec`` 路由到 SQLite；本模块中的
``FactorLoader``、YAML 索引和 ``assets/factors`` 仅用于显式旧库/迁移兼容。
Loader 只负责加载，不参与因子计算。
"""

from __future__ import annotations

import importlib
import inspect
import shutil
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable

import yaml

from app.models.factor_backtest import FactorBacktestSpec
from app.services.factor.base import BaseFactor, FactorLibrary, library_factors
from app.services.factor.sqlite_loader import (
    FactorDatabaseError,
    SQLiteFactorRepository,
    SQLiteFactorLoader,
)


class FactorLoader:
    """动态因子加载器。"""

    def __init__(self, factor_dir: str | None = None) -> None:
        if factor_dir is None:
            from app.utils.paths import factor_library_dir

            factor_dir = str(factor_library_dir())
        self.factor_dir: str = factor_dir
        self.factors: Dict[str, BaseFactor] = {}

    # -- 内部：确保 factor_dir 可被 import --
    def _ensure_importable(self) -> str:
        """把 factor_dir 加入 sys.path 并返回。"""
        p = Path(self.factor_dir).resolve()
        if not p.exists():
            raise FileNotFoundError(f"因子目录不存在: {p}")
        pkg_dir = str(p)
        if pkg_dir not in sys.path:
            sys.path.insert(0, pkg_dir)
        return pkg_dir

    @staticmethod
    def _find_classes(module):
        """在模块中查找 FactorLibrary 子类与 BaseFactor 子类（均限本模块定义）。"""
        lib_cls = None
        factor_cls = None
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            if issubclass(obj, FactorLibrary):
                lib_cls = lib_cls or obj
            elif issubclass(obj, BaseFactor):
                factor_cls = factor_cls or obj
        return lib_cls, factor_cls

    def load(self, module_name: str):
        """动态加载因子模块。

        - 若模块含 ``FactorLibrary`` 子类：实例化并注册其全部方法因子，返回库实例；
        - 否则查找首个 ``BaseFactor`` 子类，注册并返回该因子。

        Parameters
        ----------
        module_name:
            模块名。可为 ``"alpha_library"``（在 factor_dir 下查找）或带点的
            ``"factor.alpha_library"``。
        """
        self._ensure_importable()
        bare = module_name.split(".")[-1]
        module = importlib.import_module(bare)
        lib_cls, factor_cls = self._find_classes(module)

        if lib_cls is not None:
            library = lib_cls()
            for name, factor in library_factors(library).items():
                self.factors[name] = factor
            return library

        if factor_cls is not None:
            try:
                factor = factor_cls()
            except TypeError as exc:  # pragma: no cover
                raise RuntimeError(
                    f"因子 {factor_cls.__name__} 构造需要参数，无法自动实例化"
                ) from exc
            self.factors[factor.name] = factor
            return factor

        raise RuntimeError(
            f"模块 {module_name} 中未找到 FactorLibrary 或 BaseFactor 子类"
        )

    def load_all(self) -> Dict[str, BaseFactor]:
        """加载 factor_dir 下所有 ``.py`` 因子文件。"""
        p = Path(self.factor_dir).resolve()
        for py in sorted(p.glob("*.py")):
            if py.name.startswith("_"):
                continue
            try:
                self.load(py.stem)
            except Exception:  # pragma: no cover - 跳过无法加载的文件
                continue
        return self.factors

    def register(self, name: str, factor: BaseFactor) -> None:
        """手动注册因子。"""
        if not isinstance(factor, BaseFactor):
            raise TypeError(f"只能注册 BaseFactor 子类，得到 {type(factor).__name__}")
        self.factors[name] = factor


def _builtin_factor_library_index() -> dict[str, dict]:
    """读取内置因子库索引。"""

    from app.utils.paths import factor_index_path

    index_path = factor_index_path()
    if not index_path.is_file():
        raise FileNotFoundError(f"因子库索引不存在: {index_path}")
    try:
        payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"因子库索引无法解析: {index_path}") from exc

    libraries = payload.get("libraries") if isinstance(payload, dict) else None
    if not isinstance(libraries, dict):
        raise ValueError(f"因子库索引缺少 libraries 映射: {index_path}")
    invalid = [
        name
        for name, metadata in libraries.items()
        if not isinstance(name, str) or not name or not isinstance(metadata, dict)
    ]
    if invalid:
        raise ValueError(f"因子库索引包含无效库条目: {invalid}")
    return libraries


def builtin_factor_library_names() -> tuple[str, ...]:
    """返回索引中登记的内置因子库名。"""

    return tuple(sorted(_builtin_factor_library_index()))


def _builtin_factor_library_entry(library_name: str) -> tuple[Path, str, dict]:
    """解析并校验内置因子库的实现文件。"""

    from app.utils.paths import factor_library_dir

    libraries = _builtin_factor_library_index()
    metadata = libraries.get(library_name)
    if metadata is None:
        raise ValueError(
            f"不支持的内置因子库 {library_name!r}；可用: "
            f"{list(builtin_factor_library_names())}"
        )

    file_name = metadata.get("file")
    file_path = Path(file_name) if isinstance(file_name, str) else None
    factor_dir = factor_library_dir()
    if (
        file_path is None
        or file_path.name != file_name
        or file_path.suffix != ".py"
        or not (factor_dir / file_path).is_file()
    ):
        raise ValueError(
            f"因子库 {library_name!r} 在 index.yaml 中声明的实现文件无效: "
            f"{file_name!r}"
        )
    return factor_dir, file_path.stem, metadata


def _load_builtin_factor_library(library_name: str):
    """按 index.yaml 的文件声明加载并校验一个内置因子库。"""

    factor_dir, module_name, metadata = _builtin_factor_library_entry(library_name)
    loader = FactorLoader(factor_dir=str(factor_dir))
    library = loader.load(module_name)

    registered_factors = metadata.get("factors")
    if not isinstance(registered_factors, list):
        raise ValueError(
            f"因子库 {library_name!r} 尚未由 factor_catalog 同步完整因子清单"
        )
    registered_names = [
        item.get("name")
        for item in registered_factors
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    actual_names = sorted(loader.factors)
    if len(registered_names) != len(set(registered_names)) or sorted(registered_names) != actual_names:
        missing = sorted(set(actual_names) - set(registered_names))
        extra = sorted(set(registered_names) - set(actual_names))
        raise ValueError(
            f"因子库 {library_name!r} 与 index.yaml 未同步；"
            f"源码新增未登记: {missing}; 索引中不存在: {extra}"
        )
    if metadata.get("factor_count") != len(actual_names):
        raise ValueError(
            f"因子库 {library_name!r} 的 factor_count 与源码不一致；"
            f"索引: {metadata.get('factor_count')}; 源码: {len(actual_names)}"
        )
    expected_class = metadata.get("class")
    if expected_class and type(library).__name__ != expected_class:
        raise ValueError(
            f"因子库 {library_name!r} 的 class 与源码不一致；"
            f"索引: {expected_class}; 源码: {type(library).__name__}"
        )
    return loader, library


def _wrap_factor_code(factor_code: str) -> str:
    """自动补全用户因子源码所需的 FactorLibrary 外壳。"""

    wrapped = (
        'from app.services.factor.base import FactorLibrary\n\n'
        'import numpy as np\n'
        'import pandas as pd\n'
        'try:\n'
        '    from app.services.factor.sqlite_loader import load_factor_tool\n'
        '    tool = load_factor_tool()\n'
        'except (FileNotFoundError, ImportError):\n'
        '    from app.services.factor import tool\n\n'
        'class UserFactorLibrary(FactorLibrary):\n'
        '    author = "user"\n\n'
    )
    for line in factor_code.splitlines():
        wrapped += f"    {line}\n" if line.strip() else "\n"
    return wrapped


def _attach_database_library_methods(
    target_library,
    library_names: Iterable[str],
) -> None:
    """将 SQLite 因子库方法作为用户组合因子的方法依赖注入临时库。"""

    loader = SQLiteFactorLoader()
    library_type = type(target_library)
    for library_name in library_names:
        source_library = loader.load_library(library_name)
        for factor_name, factor in library_factors(source_library).items():
            if hasattr(target_library, factor_name):
                raise ValueError(f"SQLite 因子 {factor_name!r} 与自定义因子方法重名")

            def database_method(self, _factor=factor):
                return _factor.compute(self._panel)

            setattr(library_type, factor_name, database_method)


def _attach_builtin_library_methods(target_library, library_names: list[str]) -> None:
    """将 SQLite 或迁移期旧库因子注入用户组合因子。"""

    library_type = type(target_library)
    database_names: set[str] = set()
    try:
        database_repository = SQLiteFactorRepository()
        database_libraries = {
            str(library_name)
            for library_name in library_names
            if database_repository.has_library(library_name)
        }
    except (FileNotFoundError, FactorDatabaseError, sqlite3.Error):
        # 外部数据库尚未配置时，保留自定义因子的旧文件兼容路径。
        database_libraries = set()
    database_names = set(database_libraries)
    if database_libraries:
        _attach_database_library_methods(target_library, database_libraries)

    for library_name in library_names:
        if library_name in database_names:
            continue
        _loader, source_library = _load_builtin_factor_library(library_name)
        for factor_name, factor in library_factors(source_library).items():
            if hasattr(target_library, factor_name):
                raise ValueError(f"内置因子 {factor_name!r} 与自定义因子方法重名")

            def builtin_method(self, _factor=factor):
                return _factor.compute(self._panel)

            setattr(library_type, factor_name, builtin_method)


def _load_factor_from_code(
    factor_code: str,
    factor_name: str,
    library_names: list[str] | None = None,
):
    """从源码字符串生成 FactorLibrary 并返回指定因子。"""

    full_code = _wrap_factor_code(factor_code)
    tmpdir = tempfile.mkdtemp(prefix="svquant_api_")
    mod_name = f"user_factor_{uuid.uuid4().hex[:8]}"
    factor_file = Path(tmpdir) / f"{mod_name}.py"
    factor_file.write_text(full_code, encoding="utf-8")

    try:
        loader = FactorLoader(factor_dir=str(tmpdir))
        library = loader.load(mod_name)
        _attach_builtin_library_methods(library, library_names or [])
        if factor_name not in loader.factors:
            raise KeyError(
                f"因子 {factor_name!r} 未找到；可用: {list(loader.factors)}"
            )
        return loader.factors[factor_name]
    finally:
        sys.modules.pop(mod_name, None)
        try:
            sys.path.remove(str(tmpdir))
        except ValueError:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


def _load_factor_from_builtin_library(library_name: str, factor_name: str):
    """从登记的内置因子库返回指定因子。"""

    loader, _library = _load_builtin_factor_library(library_name)
    if factor_name not in loader.factors:
        raise KeyError(
            f"因子 {factor_name!r} 不在内置库 {library_name!r} 中；"
            f"可用: {list(loader.factors)}"
        )
    return loader.factors[factor_name]


def load_factor_from_spec(*, spec: FactorBacktestSpec, **_kwargs: Any) -> BaseFactor:
    """按 FactorBacktestSpec 的来源字段加载或生成一个因子。"""

    if spec.factor_code is not None:
        return _load_factor_from_code(
            spec.factor_code,
            spec.factor_name,
            list(spec.library_names),
        )
    if len(spec.library_names) != 1:
        raise ValueError("内置因子规格必须包含且只能包含一个因子库")

    library_name = spec.library_names[0]
    try:
        database_repository = SQLiteFactorRepository()
        database_library = database_repository.get_library(library_name)
    except (FileNotFoundError, FactorDatabaseError, sqlite3.Error):
        database_library = None
    except KeyError:
        database_library = None
    if database_library is not None:
        return SQLiteFactorLoader().load_factor(
            source="database",
            factor_name=spec.factor_name,
            library_name=database_library.library_name,
        )

    # 迁移期兼容：只有请求的库不属于 SQLite 库时才回退到旧 assets。默认
    # 目录/API/批量入口均不会再返回这些库名。
    return _load_factor_from_builtin_library(
        library_name,
        spec.factor_name,
    )
