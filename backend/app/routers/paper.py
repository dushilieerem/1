# -*- coding: utf-8 -*-
"""模拟盘账户与结算接口。"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import require_db_user_id
from services.paper import paper_store as store
from services.paper import scheduler as paper_scheduler
from services.paper.re_client import PaperTradingReError, fetch_status
from services.paper.settlement_service import (
    PaperTradingBusy,
    PaperTradingDisabled,
    manual_settle,
    scheduler_state,
)

router = APIRouter(tags=["paper"])


def _require_account(uid: int, account_id: int) -> None:
    try:
        store.get_account_row(uid, account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模拟账户不存在") from exc


def _parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} 必须是 YYYY-MM-DD") from exc


def _re_http_error(exc: PaperTradingReError) -> HTTPException:
    status = exc.http_status or 502
    if status not in {400, 409, 422, 429, 502, 503, 504}:
        status = 502
    return HTTPException(
        status_code=status,
        detail={"error": exc.message, "code": exc.code},
    )


@router.get("/api/paper/accounts")
def paper_list_accounts(uid: int = Depends(require_db_user_id)) -> dict:
    return store.list_accounts(uid)


@router.post("/api/paper/accounts")
def paper_create_account(
    body: dict[str, Any], uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        account = store.create_account(uid, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="策略项目不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "account": account}


@router.get("/api/paper/accounts/{account_id}")
def paper_get_account(
    account_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return store.get_account(uid, account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模拟账户不存在") from exc


@router.post("/api/paper/accounts/{account_id}/status")
def paper_update_status(
    account_id: int,
    body: dict[str, Any],
    uid: int = Depends(require_db_user_id),
) -> dict:
    try:
        account = store.update_account(uid, account_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模拟账户不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "account": account}


@router.delete("/api/paper/accounts/{account_id}")
def paper_close_account(
    account_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        account = store.update_account(uid, account_id, {"status": "closed"})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模拟账户不存在") from exc
    return {"ok": True, "account": account}


@router.get("/api/paper/accounts/{account_id}/positions")
def paper_list_positions(
    account_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        store.get_account_row(uid, account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模拟账户不存在") from exc
    return {"ok": True, "positions": store.list_positions(uid, account_id)}


@router.get("/api/paper/accounts/{account_id}/orders")
def paper_list_orders(
    account_id: int,
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uid: int = Depends(require_db_user_id),
) -> dict:
    _require_account(uid, account_id)
    return store.list_orders(
        uid, account_id, start=start, end=end, limit=limit, offset=offset
    )


@router.get("/api/paper/accounts/{account_id}/fills")
def paper_list_fills(
    account_id: int,
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uid: int = Depends(require_db_user_id),
) -> dict:
    _require_account(uid, account_id)
    return store.list_fills(
        uid, account_id, start=start, end=end, limit=limit, offset=offset
    )


@router.get("/api/paper/accounts/{account_id}/equity")
def paper_list_equity(
    account_id: int,
    start: str | None = Query(None),
    end: str | None = Query(None),
    uid: int = Depends(require_db_user_id),
) -> dict:
    _require_account(uid, account_id)
    return store.list_equity(uid, account_id, start=start, end=end)


@router.get("/api/paper/accounts/{account_id}/settlements")
def paper_list_settlements(
    account_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    uid: int = Depends(require_db_user_id),
) -> dict:
    _require_account(uid, account_id)
    return store.list_settlements(uid, account_id, limit=limit, offset=offset)


@router.get("/api/paper/accounts/{account_id}/settlement-attempts")
def paper_list_attempts(
    account_id: int,
    limit: int = Query(50, ge=1, le=200),
    uid: int = Depends(require_db_user_id),
) -> dict:
    _require_account(uid, account_id)
    return store.list_attempts(uid, account_id, limit=limit)


@router.post("/api/paper/accounts/{account_id}/settle")
def paper_settle(
    account_id: int,
    body: dict[str, Any] | None = None,
    uid: int = Depends(require_db_user_id),
) -> dict:
    body = body or {}
    settlement_date = _parse_date(body.get("date") or body.get("settlement_date"), "date")
    try:
        result = manual_settle(uid, account_id, settlement_date=settlement_date)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模拟账户不存在") from exc
    except PaperTradingDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PaperTradingBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PaperTradingReError as exc:
        raise _re_http_error(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/api/paper/accounts/{account_id}/replay")
def paper_replay(
    account_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    if not scheduler_state().get("enabled"):
        raise HTTPException(status_code=503, detail="模拟盘功能已关闭")
    try:
        rolled = store.rollback_latest_settlement(uid, account_id)
        result = manual_settle(uid, account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="没有可回滚的结算") from exc
    except PaperTradingDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PaperTradingBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PaperTradingReError as exc:
        raise _re_http_error(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "rollback": rolled, "settle": result}


@router.post("/api/paper/accounts/{account_id}/sync-strategy")
def paper_sync_strategy(
    account_id: int, uid: int = Depends(require_db_user_id)
) -> dict:
    try:
        return store.sync_strategy_from_project(uid, account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模拟账户或策略项目不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/paper/status")
def paper_status(_uid: int = Depends(require_db_user_id)) -> dict:
    try:
        re_status = fetch_status()
    except PaperTradingReError as exc:
        re_status = {"status": "unavailable", "error": exc.code, "message": exc.message}
    return {
        "ok": True,
        "scheduler": scheduler_state(),
        "schedulerLastResult": paper_scheduler.last_result(),
        "re": re_status,
    }


__all__ = ["router"]
