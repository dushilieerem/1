"""目录查询业务用例。

该模块把 API 需要的目录读取编排放在应用层，路由不直接依赖 catalog
repository。返回值是普通 dataclass/字典，Pydantic DTO 只在 HTTP 边界构造。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.repositories.catalogs.strategy_catalog import StrategyCatalog
from app.services.factor.runner import (
    _builtin_factor_library_index,
    _load_builtin_factor_library,
    builtin_factor_library_names,
)


@dataclass(frozen=True)
class FactorLibraryRecord:
    name: str
    description: str | None
    factor_count: int
    tags: tuple[str, ...]


@dataclass(frozen=True)
class FactorRecord:
    name: str
    description: str | None


class CatalogQuery:
    """面向 API 的因子、策略目录查询。"""

    def list_factor_libraries(self) -> list[FactorLibraryRecord]:
        records: list[FactorLibraryRecord] = []
        for library_name, metadata in sorted(_builtin_factor_library_index().items()):
            tags = metadata.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            factor_count = metadata.get("factor_count", 0)
            if not isinstance(factor_count, int) or isinstance(factor_count, bool):
                factor_count = 0
            records.append(
                FactorLibraryRecord(
                    name=library_name,
                    description=metadata.get("description"),
                    factor_count=factor_count,
                    tags=tuple(tag for tag in tags if isinstance(tag, str)),
                )
            )
        return records

    def list_factors(self, library_name: str) -> list[FactorRecord]:
        if library_name not in builtin_factor_library_names():
            raise KeyError(library_name)
        _loader, library = _load_builtin_factor_library(library_name)
        return [
            FactorRecord(name=name, description=(method.__doc__ or "").strip() or None)
            for name, method in library._factor_methods().items()
        ]

    def list_strategies(self) -> list[dict[str, Any]]:
        return StrategyCatalog().list_assets()


__all__ = ["CatalogQuery", "FactorLibraryRecord", "FactorRecord"]
