# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.deps import require_admin, require_user
from services.data.market_data_bff import fetch_market_daily
from services.news.news_ingest import FETCHERS, UNSUPPORTED_SOURCES, enrich_news_body, ingest_news
from services.news.news_store import get_news, ingest_health, list_news
from services.news.news_tag_dict import dict_snapshot

router = APIRouter(tags=["news"])


@router.get("/api/news")
def news_list(
    category: str | None = None,
    source: str | None = None,
    q: str | None = None,
    mode: str | None = None,
    theme: list[str] | None = Query(None),
    symbol: list[str] | None = Query(None),
    industry: list[str] | None = Query(None),
    limit: int = 50,
    offset: int = 0,
) -> dict:
    try:
        return list_news(
            category=category,
            source=source,
            q=q,
            mode=mode,
            theme=theme,
            symbol=symbol,
            industry=industry,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/news/dict")
def news_dict() -> dict:
    snap = dict_snapshot()
    return {"ok": True, **snap}


@router.get("/api/news/{news_id}")
def news_get(news_id: str) -> dict:
    if not news_id.isdigit():
        raise HTTPException(status_code=400, detail="invalid id")
    try:
        return get_news(int(news_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/api/news/ingest")
def news_ingest(body: dict[str, Any], _admin: dict = Depends(require_admin)) -> JSONResponse:
    raw_sources = body.get("sources")
    sources = None
    allowed = set(FETCHERS) | set(UNSUPPORTED_SOURCES)
    if isinstance(raw_sources, list):
        sources = [str(s).strip() for s in raw_sources if str(s).strip()]
        bad = [s for s in sources if s not in allowed]
        if bad:
            return JSONResponse(
                {
                    "error": f"unsupported sources: {', '.join(bad)}",
                    "supported": list(FETCHERS.keys()),
                    "unsupported": UNSUPPORTED_SOURCES,
                },
                status_code=400,
            )
    elif isinstance(raw_sources, str) and raw_sources.strip():
        sources = [s.strip() for s in raw_sources.split(",") if s.strip()]
    try:
        limit = int(body.get("limit") or body.get("limit_per_source") or 12)
        return JSONResponse(ingest_news(sources=sources, limit_per_source=limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/admin/news/ingest-health")
def admin_news_ingest_health(
    _admin: dict = Depends(require_admin),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """P1-C07：各资讯源最近抓取成功/失败与陈旧告警。"""
    try:
        return ingest_health(limit=limit)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "warnings": [str(exc)], "runs": [], "sources": []}


@router.post("/api/news/{news_id}/enrich")
def news_enrich(news_id: str, _user: dict = Depends(require_user)) -> dict:
    if not news_id.isdigit():
        raise HTTPException(status_code=400, detail="invalid id")
    try:
        return enrich_news_body(int(news_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.get("/api/market-data/daily/{code}")
def market_daily(
    code: str,
    start: str | None = None,
    end: str | None = None,
    fresh: str = "0",
) -> JSONResponse:
    try:
        data = fetch_market_daily(
            code,
            start=start,
            end=end,
            bypass_cache=fresh in ("1", "true", "yes"),
        )
        return JSONResponse(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
