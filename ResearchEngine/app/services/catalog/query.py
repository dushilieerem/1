"""目录查询业务用例。

该模块把 API 需要的目录读取编排放在应用层，路由不直接依赖 catalog
repository。返回值是普通 dataclass/字典，Pydantic DTO 只在 HTTP 边界构造。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.catalog.strategy_catalog import StrategyCatalog
from app.services.factor.sqlite_loader import SQLiteFactorRepository


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
    factor_id: str | None = None
    display_name: str | None = None
    name_en: str | None = None
    category_name: str | None = None


class CatalogQuery:
    """面向 API 的因子、策略目录查询。"""

    def __init__(self, repository: SQLiteFactorRepository | None = None) -> None:
        self.repository = repository or SQLiteFactorRepository()

    def list_factor_libraries(self) -> list[FactorLibraryRecord]:
        records: list[FactorLibraryRecord] = []
        for library in self.repository.list_libraries():
            factors = self.repository.list_factors(
                library.library_name,
                validate_code=False,
            )
            tags = tuple(
                sorted(
                    {
                        category
                        for category in (
                            factor.category_name for factor in factors
                        )
                        if category
                    }
                )
            )
            records.append(
                FactorLibraryRecord(
                    name=library.library_name,
                    description=library.description,
                    factor_count=library.factor_count,
                    tags=tags,
                )
            )
        return records

    def list_factors(self, library_name: str) -> list[FactorRecord]:
        # 目录展示只依赖元数据；单条源码的语法/编译错误应在实际回测时
        # 隔离到对应因子，不应让整座因子库无法被浏览。
        factors = self.repository.list_factors(library_name, validate_code=False)
        return [
            FactorRecord(
                name=factor.sv_id,
                description=factor.description,
                factor_id=factor.sv_id,
                display_name=factor.factor_name,
                name_en=factor.factor_name_en,
                category_name=factor.category_name,
            )
            for factor in factors
        ]

    def list_strategies(self) -> list[dict[str, Any]]:
        return StrategyCatalog().list_assets()


__all__ = ["CatalogQuery", "FactorLibraryRecord", "FactorRecord"]
