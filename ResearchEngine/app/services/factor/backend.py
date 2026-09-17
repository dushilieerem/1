"""``ComputeBackend`` - 因子计算后端抽象。

依据 ``docs/99-历史归档/FEAT-001-QuantCore基础能力/04-class-design.md`` FactorEngine 节：

    属性：
      name: str                  -- "python" | "numba" | "cpp" | "gpu"

    方法：
      execute(func, *args) -> Any

设计上预留多后端（Python / Numba / C++ / GPU）扩展点。当前仅实现
``PythonBackend``（开箱即用）；新增真实后端时在 :data:`BACKENDS` 注册即可，
无需改动 :class:`FactorEngine`。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class ComputeBackend(ABC):
    """计算后端抽象基类。"""

    #: 后端名称
    name: str = "base"

    @abstractmethod
    def execute(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """执行因子计算函数。"""


class PythonBackend(ComputeBackend):
    """CPython 原生执行后端（默认）。"""

    name = "python"

    def execute(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)


#: 后端名称 -> 后端类。新增后端（如 Numba）实现 ``ComputeBackend`` 后在此注册。
BACKENDS = {
    "python": PythonBackend,
}


def get_backend(name: str = "python") -> ComputeBackend:
    """按名称获取计算后端实例。"""
    if name not in BACKENDS:
        raise ValueError(
            f"未知计算后端 {name!r}，可选: {list(BACKENDS)}"
        )
    return BACKENDS[name]()
