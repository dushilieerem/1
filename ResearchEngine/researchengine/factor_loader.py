"""``FactorLoader`` - 动态加载因子文件。

依据 ``docs/04-类设计.md`` FactorLoader 节：

    属性：
      factor_dir: str
      factors: Dict[str, BaseFactor]

    方法：
      load(module_name: str) -> BaseFactor
      load_all() -> Dict[str, BaseFactor]
      register(name: str, factor: BaseFactor)

动态加载方式：``importlib.import_module``。Loader 只负责加载，不参与因子计算。
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Dict

from quantcore.factor.base import BaseFactor, FactorLibrary, library_factors


class FactorLoader:
    """动态因子加载器。"""

    def __init__(self, factor_dir: str = "factor") -> None:
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
