"""因子、策略和已发布行情目录路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException

from app.utils.exceptions import MarketDataError
from app.schemas.backtest import (
    DailyBar,
    DailyBarsResponse,
    DateRange,
    FactorInfo,
    FactorLibraryInfo,
    FactorLibraryListResponse,
    FactorListResponse,
    IndexConstituentsResponse,
    IndexInfo,
    IndexListResponse,
    StrategyInfo,
    StrategyListResponse,
    StockInfo,
    SymbolListResponse,
)
from app.services.catalog.query import CatalogQuery
from app.services.factor.market_data import (
    get_daily_bars,
    get_index_constituents,
    get_indices,
    get_symbols,
)


router = APIRouter()
_catalog = CatalogQuery()


def _market_call(function, *args):
    try:
        return function(*args)
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/factor-libraries", response_model=FactorLibraryListResponse)
def list_factor_libraries() -> FactorLibraryListResponse:
    try:
        return FactorLibraryListResponse(
            libraries=[
                FactorLibraryInfo(
                    name=record.name,
                    description=record.description,
                    factor_count=record.factor_count,
                    tags=list(record.tags),
                )
                for record in _catalog.list_factor_libraries()
            ]
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"因子库目录不可用: {exc}") from exc


@router.get("/factors/{library_name}", response_model=FactorListResponse)
def list_library_factors(library_name: str) -> FactorListResponse:
    try:
        factors = _catalog.list_factors(library_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未找到内置因子库: {library_name}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"因子库 {library_name!r} 不可用: {exc}",
        ) from exc
    return FactorListResponse(
        library_name=library_name,
        factors=[
            FactorInfo(
                name=record.name,
                description=record.description,
                factor_id=record.factor_id,
                display_name=record.display_name,
                name_en=record.name_en,
                category_name=record.category_name,
            )
            for record in factors
        ],
    )


@router.get("/strategies", response_model=StrategyListResponse)
def list_strategies() -> StrategyListResponse:
    return StrategyListResponse(
        strategies=[StrategyInfo.model_validate(item) for item in _catalog.list_strategies()]
    )


@router.get("/market-data/daily/{symbol}", response_model=DailyBarsResponse)
def daily_bars(symbol: str, start: date | None = None, end: date | None = None) -> DailyBarsResponse:
    result = _market_call(get_daily_bars, symbol, start, end)
    return DailyBarsResponse(
        symbol=result.symbol,
        name=result.name,
        bars=[DailyBar(**bar.__dict__) for bar in result.bars],
        date_range=DateRange(**result.date_range.__dict__),
    )


@router.get("/market-data/symbols", response_model=SymbolListResponse)
def list_market_data_symbols() -> SymbolListResponse:
    result = _market_call(get_symbols)
    return SymbolListResponse(
        symbols=[StockInfo(**item.__dict__) for item in result.symbols],
        unmapped_count=result.unmapped_count,
    )


@router.get("/market-data/indices", response_model=IndexListResponse)
def list_market_data_indices() -> IndexListResponse:
    result = _market_call(get_indices)
    return IndexListResponse(
        indices=[IndexInfo(**item.__dict__) for item in result.indices]
    )


@router.get("/market-data/indices/{code}/constituents", response_model=IndexConstituentsResponse)
def list_index_constituents(code: str) -> IndexConstituentsResponse:
    result = _market_call(get_index_constituents, code)
    return IndexConstituentsResponse(
        index=IndexInfo(**result.index.__dict__),
        constituents=[StockInfo(**item.__dict__) for item in result.constituents],
        unmapped_count=result.unmapped_count,
    )


def _builtin_factors(library_name: str | None = None) -> list[FactorInfo]:
    """保留路由测试使用的 API 边界辅助函数。"""

    names = (library_name,) if library_name is not None else None
    records = []
    for current in names or [record.name for record in _catalog.list_factor_libraries()]:
        records.extend(_catalog.list_factors(current))
    return [
        FactorInfo(
            name=record.name,
            description=record.description,
            factor_id=record.factor_id,
            display_name=record.display_name,
            name_en=record.name_en,
            category_name=record.category_name,
        )
        for record in records
    ]


__all__ = ["router", "_builtin_factors"]
