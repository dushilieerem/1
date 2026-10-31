# -*- coding: utf-8 -*-
"""市场数据：服务端证券搜索（P1-D04）。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

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
