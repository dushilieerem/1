"""共享的 SQLite 内置因子测试支持。

生产代码已经从按文件拆分的因子库迁移到 SQLite ``主因子库``。测试通过这个
小适配器复用当前加载契约，避免每个因子测试重新编译 432 个源码函数。
"""

from __future__ import annotations

from functools import lru_cache

from app.services.factor.base import library_factors
from app.services.factor.sqlite_loader import (
    SQLiteFactorLoader,
    SQLiteFactorRepository,
)
from app.utils.paths import factor_database_path


BUILTIN_LIBRARY_NAME = "主因子库"


@lru_cache(maxsize=1)
def _builtin_library_type():
    """编译并缓存主因子库类型，而不是共享可变的库实例。"""

    library = SQLiteFactorLoader().load_library(BUILTIN_LIBRARY_NAME)
    return type(library)


def builtin_library():
    """返回一个新的主因子库实例，避免测试之间共享 ``_panel``。"""

    return _builtin_library_type()()


def builtin_factors():
    """返回以源码函数名索引的当前内置因子适配器。"""

    return library_factors(builtin_library())


class BuiltinFactorLoader:
    """保留测试所需的 ``FactorLoader`` 形状，但只加载当前内置库。"""

    def __init__(self):
        self.factors = {}

    def load(self, library_name: str = BUILTIN_LIBRARY_NAME):
        if library_name != BUILTIN_LIBRARY_NAME:
            raise ValueError(
                f"当前内置因子测试只支持 {BUILTIN_LIBRARY_NAME!r}，得到 {library_name!r}"
            )
        library = builtin_library()
        self.factors = library_factors(library)
        return library


@lru_cache(maxsize=1)
def builtin_factor_ids() -> dict[str, str]:
    """返回源码函数名到稳定 SV 因子 ID 的映射。"""

    return {
        record.function_name: record.sv_id
        for record in SQLiteFactorRepository(factor_database_path()).list_factors(
            BUILTIN_LIBRARY_NAME
        )
    }


__all__ = [
    "BUILTIN_LIBRARY_NAME",
    "BuiltinFactorLoader",
    "builtin_factor_ids",
    "builtin_factors",
    "builtin_library",
]
