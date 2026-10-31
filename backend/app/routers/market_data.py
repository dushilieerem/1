# -*- coding: utf-8 -*-
"""市场数据：服务端证券搜索（P1-D04）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from services.data import indicators as ind
from services.data import marketdata_store as md
from services.marketdata.store import count_securities, search_securities

router = APIRouter(prefix="/api/market-data", tags=["market-data"])


@router.get("/search")
def search(
    q: str = Query("", max_length=64),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    term = (q or "").strip()
    if not term:
        return {"ok": True, "items": [], "total": 0, "limit": limit, "offset": offset}
    return {
        "ok": True,
        "items": search_securities(term, limit=limit, offset=offset),
        "total": count_securities(term),
        "limit": limit,
        "offset": offset,
    }


@router.get("/minute/{symbol}")
def minute(
    symbol: str,
    start: str = Query(""),
    end: str = Query(""),
    limit_days: int = Query(5, ge=1, le=30),
) -> dict[str, Any]:
    """P1-D02：1 分钟行情（单日分区读取，带数据版本）。"""
    try:
        return md.minute_bars(symbol, start=start, end=end, limit_days=limit_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"本地行情数据不可用: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/fundamentals/{symbol}")
def fundamentals(
    symbol: str,
    start: str = Query(""),
    end: str = Query(""),
) -> dict[str, Any]:
    """P1-D01：点时估值/状态字段（当前 release 可用的基本面字段）。"""
    try:
        return md.fundamentals(symbol, start=start, end=end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/daily-local/{symbol}")
def daily_local(
    symbol: str,
    start: str = Query(""),
    end: str = Query(""),
    adjusted: bool = Query(True),
) -> dict[str, Any]:
    """本地日线（含成交量/额），用于图表与指标计算。"""
    try:
        return md.daily_bars(symbol, start=start, end=end, adjusted=adjusted)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/indices/catalog")
def indices_catalog() -> dict[str, Any]:
    """P1-D03：从数据 release 动态列出指数。"""
    return md.index_catalog()


@router.get("/fields/samples")
def fields_samples() -> dict[str, Any]:
    """P1-D08：字段字典真实样例与数据版本。"""
    return md.field_catalog_samples()


@router.get("/availability")
def availability() -> dict[str, Any]:
    """P1-D06：按数据可用性开放品种；不可用项返回明确原因。"""
    idx = md.index_catalog()
    manifest = md.data_manifest()
    return {
        "ok": True,
        "data_version": manifest.get("data_version"),
        "categories": [
            {"id": "stock", "label": "A 股", "available": True},
            {
                "id": "index",
                "label": "指数",
                "available": bool(idx.get("items")),
                "count": idx.get("count", 0),
                "reason": None if idx.get("items") else "当前 release 未发布指数行情",
            },
            {
                "id": "sector",
                "label": "板块",
                "available": True,
                "reason": "按申万行业字段筛选；行业映射随 release 更新",
            },
            {
                "id": "etf",
                "label": "ETF",
                "available": False,
                "reason": "当前 release 未发布 ETF 行情",
            },
            {
                "id": "futures",
                "label": "期货",
                "available": False,
                "reason": "当前 release 未发布期货行情",
            },
        ],
    }


@router.get("/indicators/{symbol}")
def technical_indicators(
    symbol: str,
    start: str = Query(""),
    end: str = Query(""),
    indicators: str = Query("ma,macd,rsi,boll"),
    ma5: int = Query(5, ge=1, le=250),
    ma10: int = Query(10, ge=1, le=250),
    ma20: int = Query(20, ge=1, le=250),
    ma60: int = Query(60, ge=1, le=250),
) -> dict[str, Any]:
    """P1-D07：服务端计算技术指标（参数可配）。"""
    try:
        bars = md.daily_bars(symbol, start=start, end=end)
        wanted = [x for x in (indicators or "").split(",") if x.strip()]
        params = {"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60}
        computed = ind.compute(bars["items"], indicators=wanted, params=params)
        return {
            "ok": True,
            "symbol": bars["symbol"],
            "frequency": "1d",
            "bars": bars["items"],
            "data_version": bars.get("data_version"),
            **computed,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
