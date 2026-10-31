# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_db_user_id, soft_db_user_id
from services.marketdata.store import latest_bar
from services.data.watchlist_store import (
    add_watchlist_symbol,
    add_watchlist_symbols_batch,
    create_watchlist,
    delete_watchlist,
    delete_watchlist_symbol,
    list_watchlist_symbols,
    list_watchlists,
    rename_watchlist,
)

router = APIRouter(tags=["watchlists"])


@router.get("/api/watchlists")
def watchlists_list(uid: int | None = Depends(soft_db_user_id)) -> dict:
    if uid is None:
        return {"ok": True, "watchlists": []}
    return {"ok": True, "watchlists": list_watchlists(uid)}


@router.post("/api/watchlists")
def watchlists_create(
    body: dict[str, Any], uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        wl = create_watchlist(uid, str(body.get("name") or ""))
        return {"ok": True, "watchlist": wl}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/watchlists/{wl_id}/symbols")
def watchlists_symbols(wl_id: int, uid: int = Depends(require_db_user_id)) -> dict:
    try:
        rows = list_watchlist_symbols(uid, wl_id)
        for row in rows:
            bar = latest_bar(str(row.get("symbol") or ""), adjust="none")
            if bar:
                close = bar.get("close")
                prev = bar.get("pre_close")
                row["price"] = close
                row["changePct"] = (float(close) / float(prev) - 1) if close and prev else None
                row["asOf"] = bar.get("trade_date")
        return {"ok": True, "symbols": rows}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/api/watchlists/{wl_id}/symbols/batch")
def watchlists_symbols_batch(
    wl_id: int,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return add_watchlist_symbols_batch(
            uid, wl_id, items=body.get("items") or []
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/watchlists/{wl_id}/symbols")
def watchlists_add_symbol(
    wl_id: int,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return add_watchlist_symbol(
            uid,
            wl_id,
            symbol=str(body.get("symbol") or ""),
            name=str(body.get("name") or ""),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/watchlists/{wl_id}")
def watchlists_rename(
    wl_id: int,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        wl = rename_watchlist(uid, wl_id, str(body.get("name") or ""))
        return {"ok": True, "watchlist": wl}
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/watchlists/{wl_id}/symbols/{symbol}")
def watchlists_delete_symbol(
    wl_id: int,
    symbol: str,
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        return delete_watchlist_symbol(uid, wl_id, symbol)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/watchlists/{wl_id}")
def watchlists_delete(wl_id: int, uid: int = Depends(require_db_user_id)) -> dict:
    try:
        return delete_watchlist(uid, wl_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found") from None
