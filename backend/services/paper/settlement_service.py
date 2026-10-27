# -*- coding: utf-8 -*-
"""模拟盘结算编排：取 RE 结果、校验、单事务落账、失败重试。"""
from __future__ import annotations

import time
import uuid
from datetime import date, timedelta
from typing import Any

from services.core.env_config import env
from services.paper import paper_store as store
from services.paper.re_client import (
    PaperTradingReError,
    fetch_status,
    settle as re_settle,
)


class PaperTradingDisabled(RuntimeError):
    pass


class PaperTradingBusy(RuntimeError):
    pass


class PaperTradingSettled(RuntimeError):
    """账户当天已结算；调用方可按幂等结果处理。"""

    def __init__(self, settlement: dict[str, Any]) -> None:
        super().__init__("already settled")
        self.settlement = settlement


BLOCKING_CODES = {
    "CODE_HASH_MISMATCH",
    "STRATEGY_STATE_VERSION_MISMATCH",
    "STRATEGY_STATE_HASH_MISMATCH",
    "UNSUPPORTED_PORTFOLIO",
    "TARGET_WEIGHT_EXCEEDS_ONE",
    "STRATEGY_CODE_INVALID",
    "STRATEGY_STATE_UNSERIALIZABLE",
    "STRATEGY_STATE_TOO_LARGE",
}
RETRYABLE_CODES = {"DATA_NOT_READY", "RE_TIMEOUT", "RE_UNAVAILABLE", "RE_BUSY", "HTTP_429"}


def _bool_env(name: str, default: bool) -> bool:
    raw = (env(name, "1" if default else "0") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(env(name, str(default)) or default))
    except (TypeError, ValueError):
        return default


def enabled() -> bool:
    return _bool_env("SVQUANT_PAPER_TRADING_ENABLED", True)


def settle_timeout() -> int:
    return _int_env("SVQUANT_PAPER_SETTLE_TIMEOUT_SEC", 300, minimum=30)


def max_catchup_days() -> int:
    return _int_env("SVQUANT_PAPER_MAX_CATCHUP_DAYS", 10, minimum=1)


def max_retry() -> int:
    return _int_env("SVQUANT_PAPER_MAX_RETRY", 5, minimum=1)


def retry_backoff_sec() -> int:
    return _int_env("SVQUANT_PAPER_RETRY_BACKOFF_SEC", 300, minimum=30)


def _positions(user_id: int, account_id: int) -> list[dict[str, Any]]:
    return [
        {
            "symbol": item["symbol"],
            "quantity": int(item["quantity"]),
            "available_quantity": int(item["availableQuantity"]),
            "average_cost": float(item["averageCost"]),
        }
        for item in store.list_positions(user_id, account_id)
        if int(item["quantity"]) > 0
    ]


def build_settlement_payload(
    account: dict[str, Any], *, settlement_date: date
) -> dict[str, Any]:
    user_id = int(account["user_id"])
    account_id = int(account["id"])
    state = account.get("strategy_state") or None
    payload: dict[str, Any] = {
        "settlement_date": settlement_date.isoformat(),
        "engine_mode": account["engine_mode"],
        "strategy_code": account["strategy_code"],
        "expected_code_hash": account["code_hash"],
        "universe": account["universe"],
        "benchmark": account["benchmark"],
        "account": {
            "cash": float(account["cash"]),
            "positions": _positions(user_id, account_id),
        },
        "execution": {
            "commission_rate": float(account["commission_rate"]),
            "min_commission": float(account["min_commission"]),
            "stamp_tax_rate": float(account["stamp_tax"]),
            "slippage_rate": float(account["slippage_rate"]),
            "lot_size": int(account["lot_size"]),
            "history_days": 900,
            "filter_st": bool(account["filter_st"]),
        },
    }
    if state:
        payload["strategy_state"] = state
        payload["strategy_state_code_hash"] = account["code_hash"]
        if account.get("state_hash"):
            payload["expected_state_hash"] = account["state_hash"]
    return payload


def settle_account_day(
    user_id: int,
    account_id: int,
    *,
    settlement_date: date | None = None,
    trigger: str = "manual",
) -> dict[str, Any]:
    """结算账户的下一交易日；返回结算或跳过结果。"""

    account = store.get_account_row(user_id, account_id)
    if account["status"] != "active":
        raise ValueError("账户不是 active 状态")
    next_raw = account.get("next_settlement_date")
    next_date = next_raw if isinstance(next_raw, date) else date.fromisoformat(str(next_raw))
    target = settlement_date or next_date
    if target != next_date:
        existing = store.find_applied_settlement(user_id, account_id, target)
        if existing:
            return {"settled": True, "idempotent": True, "settlement": existing}
        raise ValueError(
            f"结算日不连续：期望 {next_date.isoformat()}，收到 {target.isoformat()}"
        )

    existing = store.find_applied_settlement(user_id, account_id, target)
    if existing:
        return {"settled": True, "idempotent": True, "settlement": existing}

    owner = f"svquant:{uuid.uuid4().hex[:10]}"
    lease_ttl = settle_timeout() + 60
    if not store.claim_settlement_lease(user_id, account_id, owner=owner, ttl_sec=lease_ttl):
        raise PaperTradingBusy("账户正在由其他结算任务处理")
    attempt_id: int | None = None
    started = time.monotonic()
    try:
        status = fetch_status(target.isoformat())
        status_value = str(status.get("status") or "")
        if status_value == "not_trading_day":
            next_after = status.get("next_trading_day")
            if next_after:
                next_date = date.fromisoformat(str(next_after))
            else:
                next_date = target + timedelta(days=1)
                while next_date.weekday() >= 5:
                    next_date += timedelta(days=1)
            store.advance_next_settlement_date(user_id, account_id, next_date)
            return {"settled": False, "skipped": "not_trading_day", "status": status}
        if status_value != "ready":
            # 目标日晚于行情已就绪日 = 该交易日数据尚未发布，属于正常等待，
            # 不是账户错误。若在此写 last_error，调度器结算完最新一日后紧接着
            # 轮询下一日，会把健康账户每天都标成 DATA_NOT_READY。
            latest_ready_raw = status.get("latest_ready_trading_day")
            pending_release = False
            if status_value == "data_not_ready" and latest_ready_raw:
                try:
                    pending_release = date.fromisoformat(str(latest_ready_raw)) < target
                except ValueError:
                    pending_release = False
            if pending_release:
                return {"settled": False, "skipped": "data_not_ready", "status": status}
            store.mark_account_error(
                user_id,
                account_id,
                code="DATA_NOT_READY",
                message=str(status.get("status") or "data_not_ready"),
                blocked=False,
            )
            return {"settled": False, "skipped": "data_not_ready", "status": status}

        payload = build_settlement_payload(account, settlement_date=target)
        attempt_id = store.start_attempt(
            user_id,
            account_id,
            settlement_date=target,
            trigger=trigger,
            request_payload=payload,
        )
        response = re_settle(payload, timeout=settle_timeout())
        if str(response.get("settlement_date")) != target.isoformat():
            raise PaperTradingReError(
                code="SETTLEMENT_DATE_MISMATCH",
                message=(
                    f"RE 返回结算日 {response.get('settlement_date')}，"
                    f"期望 {target.isoformat()}"
                ),
            )
        if str(response.get("code_hash") or "") != str(account["code_hash"]):
            raise PaperTradingReError(
                code="CODE_HASH_MISMATCH",
                message="RE 返回的策略代码哈希与账户快照不一致",
            )
        applied = store.apply_settlement(
            user_id,
            account_id,
            response=response,
            request_meta={"config_revision": int(account.get("config_revision") or 1)},
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        store.finish_attempt(
            attempt_id,
            status="settled",
            http_status=200,
            response=response,
            data_release_id=response.get("data_release_id"),
            data_release_signature=response.get("data_release_signature"),
            duration_ms=duration_ms,
        )
        return {
            "settled": True,
            "idempotent": bool(applied.get("idempotent")),
            "settlement": applied["settlement"],
            "account": store.get_account(user_id, account_id)["account"],
        }
    except PaperTradingReError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        if attempt_id is not None:
            store.finish_attempt(
                attempt_id,
                status="failed",
                http_status=exc.http_status,
                error_code=exc.code,
                error_message=exc.message,
                duration_ms=duration_ms,
            )
        if exc.code == "NOT_A_TRADING_DAY":
            next_after = None
            if isinstance(exc.detail, dict):
                next_after = (exc.detail.get("detail") or {}).get("next_trading_day")
            next_date = (
                date.fromisoformat(str(next_after))
                if next_after
                else target + timedelta(days=1)
            )
            store.advance_next_settlement_date(user_id, account_id, next_date)
            return {"settled": False, "skipped": "not_trading_day", "error": exc.code}
        if exc.code in BLOCKING_CODES or (exc.http_status == 422):
            store.mark_account_error(
                user_id, account_id, code=exc.code, message=exc.message, blocked=True
            )
        else:
            retry_count = int(account.get("retry_count") or 0) + 1
            delay = min(retry_backoff_sec() * retry_count, 3600)
            store.mark_account_error(
                user_id,
                account_id,
                code=exc.code,
                message=exc.message,
                blocked=False,
                retry_delay_sec=delay,
            )
        raise
    except Exception as exc:  # noqa: BLE001 - 保证尝试记录不长期停在 running
        if attempt_id is not None:
            store.finish_attempt(
                attempt_id,
                status="failed",
                error_code=type(exc).__name__,
                error_message=str(exc),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        raise
    finally:
        store.release_settlement_lease(user_id, account_id, owner)


def manual_settle(
    user_id: int,
    account_id: int,
    *,
    settlement_date: date | None = None,
) -> dict[str, Any]:
    if not enabled():
        raise PaperTradingDisabled("模拟盘功能已关闭")
    if settlement_date is not None:
        return settle_account_day(
            user_id, account_id, settlement_date=settlement_date, trigger="manual"
        )
    status = fetch_status()
    latest_raw = status.get("latest_ready_trading_day")
    if not latest_raw:
        return {"settled": False, "skipped": "data_not_ready", "status": status}
    latest = date.fromisoformat(str(latest_raw))
    results: list[dict[str, Any]] = []
    for _ in range(max_catchup_days()):
        account = store.get_account_row(user_id, account_id)
        next_raw = account.get("next_settlement_date")
        next_date = next_raw if isinstance(next_raw, date) else date.fromisoformat(str(next_raw))
        if next_date > latest:
            break
        result = settle_account_day(user_id, account_id, trigger="manual")
        results.append(result)
        if result.get("skipped") == "not_trading_day":
            continue
        if result.get("skipped") or not result.get("settled"):
            break
    return {
        "settled": bool(results) and all(item.get("settled") for item in results),
        "latestReadyDate": latest.isoformat(),
        "results": results,
    }


def run_scheduler_tick(*, reason: str = "scheduled", limit: int = 50) -> dict[str, Any]:
    if not enabled():
        return {"ok": True, "disabled": True, "reason": reason}
    try:
        status = fetch_status()
    except PaperTradingReError as exc:
        return {"ok": False, "reason": reason, "error": exc.code, "message": exc.message}
    latest_raw = status.get("latest_ready_trading_day")
    if not latest_raw:
        return {"ok": True, "reason": reason, "latestReadyDate": None, "accounts": 0}
    latest = date.fromisoformat(str(latest_raw))
    accounts = store.list_due_accounts(latest, limit=limit)
    settled = failed = 0
    for account in accounts:
        user_id = int(account["user_id"])
        account_id = int(account["id"])
        for _ in range(max_catchup_days()):
            row = store.get_account_row(user_id, account_id)
            next_raw = row.get("next_settlement_date")
            next_date = (
                next_raw if isinstance(next_raw, date) else date.fromisoformat(str(next_raw))
            )
            if next_date > latest:
                # 已补到最新可用交易日，下一日的行情还没发布，停止推进。
                # 少了这个守卫，结算成功后同一次 tick 会立刻用未发布日问 RE，
                # 把账户误标为 DATA_NOT_READY。
                break
            try:
                result = settle_account_day(
                    user_id, account_id, trigger=f"scheduler:{reason}"
                )
            except Exception as exc:  # noqa: BLE001 - 单账户失败不阻断其他账户
                failed += 1
                print(
                    f"[paper] account={account_id} settle failed: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                break
            if result.get("settled"):
                settled += 1
                continue
            if result.get("skipped") == "not_trading_day":
                # 非交易日已推进 next_settlement_date，继续尝试下一个日期。
                continue
            break
    return {
        "ok": failed == 0,
        "reason": reason,
        "latestReadyDate": latest.isoformat(),
        "accounts": len(accounts),
        "settled": settled,
        "failed": failed,
    }


def scheduler_state() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "activeAccounts": store.active_accounts_count(),
        "maxCatchupDays": max_catchup_days(),
        "settleTimeoutSec": settle_timeout(),
        "retryBackoffSec": retry_backoff_sec(),
    }


__all__ = [
    "PaperTradingBusy",
    "PaperTradingDisabled",
    "PaperTradingSettled",
    "build_settlement_payload",
    "enabled",
    "manual_settle",
    "run_scheduler_tick",
    "scheduler_state",
    "settle_account_day",
]
