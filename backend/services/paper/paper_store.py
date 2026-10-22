# -*- coding: utf-8 -*-
"""模拟盘账户、持仓、订单、成交与结算账本。

- 账户与策略项目解耦：创建时快照源码/执行模式/股票池/费用，项目后续修改
  不会自动影响已有账户。
- ``paper_settlements`` 的部分唯一索引保证同一账户同一交易日只有一条
  ``applied`` 结算；失败只写 ``paper_settlement_attempts``，可重试。
- 所有用户数据按 ``user_id`` 隔离。
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from typing import Any

from services.core.db import get_conn
from services.strategy.builtin_strategies_store import get_builtin_strategy
from services.strategy.strategy_store import get_project

DEFAULT_COMMISSION_RATE = 0.0003
DEFAULT_MIN_COMMISSION = 5.0
DEFAULT_STAMP_TAX = 0.0005
DEFAULT_LOT_SIZE = 100
DEFAULT_INITIAL_CASH = 1_000_000.0
MARKET_CLOSE = time(15, 0)


def ensure_paper_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_accounts (
              id                BIGSERIAL PRIMARY KEY,
              user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name              TEXT NOT NULL,
              project_id        TEXT NOT NULL,
              project_name      TEXT NOT NULL DEFAULT '',
              engine_mode       TEXT NOT NULL,
              strategy_id       TEXT,
              strategy_code     TEXT NOT NULL,
              code_hash         TEXT NOT NULL,
              strategy_config   JSONB NOT NULL DEFAULT '{}'::jsonb,
              config_revision   INTEGER NOT NULL DEFAULT 1,
              universe          TEXT NOT NULL,
              benchmark         TEXT NOT NULL DEFAULT 'CSI300',
              commission_rate   DOUBLE PRECISION NOT NULL DEFAULT 0.0003,
              min_commission    DOUBLE PRECISION NOT NULL DEFAULT 5.0,
              stamp_tax         DOUBLE PRECISION NOT NULL DEFAULT 0.0005,
              slippage_rate     DOUBLE PRECISION NOT NULL DEFAULT 0,
              lot_size          INTEGER NOT NULL DEFAULT 100,
              filter_st         BOOLEAN NOT NULL DEFAULT FALSE,
              initial_cash      DOUBLE PRECISION NOT NULL,
              cash              DOUBLE PRECISION NOT NULL,
              total_equity      DOUBLE PRECISION NOT NULL,
              positions_value   DOUBLE PRECISION NOT NULL DEFAULT 0,
              strategy_state    JSONB,
              state_hash        TEXT,
              first_settlement_date DATE NOT NULL,
              next_settlement_date  DATE NOT NULL,
              last_settled_date DATE,
              status            TEXT NOT NULL DEFAULT 'active',
              last_error_code   TEXT,
              last_error_message TEXT,
              retry_count       INTEGER NOT NULL DEFAULT 0,
              next_retry_at     TIMESTAMPTZ,
              settle_lease_owner TEXT,
              settle_lease_until TIMESTAMPTZ,
              last_settlement_release_id TEXT,
              last_settlement_release_signature TEXT,
              created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT paper_accounts_status_chk
                CHECK (status IN ('active', 'paused', 'closed', 'blocked')),
              CONSTRAINT paper_accounts_engine_mode_chk
                CHECK (engine_mode IN ('event', 'vectorized')),
              CONSTRAINT paper_accounts_user_id_key UNIQUE (user_id, id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_accounts_user_updated "
            "ON paper_accounts (user_id, updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_accounts_due "
            "ON paper_accounts (status, next_settlement_date, id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_positions (
              user_id             BIGINT NOT NULL,
              account_id          BIGINT NOT NULL,
              symbol              TEXT NOT NULL,
              quantity            BIGINT NOT NULL DEFAULT 0,
              available_quantity  BIGINT NOT NULL DEFAULT 0,
              average_cost        DOUBLE PRECISION NOT NULL DEFAULT 0,
              mark_price          DOUBLE PRECISION,
              market_value        DOUBLE PRECISION,
              updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (user_id, account_id, symbol),
              CONSTRAINT paper_positions_account_fk
                FOREIGN KEY (user_id, account_id)
                REFERENCES paper_accounts (user_id, id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_settlements (
              id                  BIGSERIAL PRIMARY KEY,
              user_id             BIGINT NOT NULL,
              account_id          BIGINT NOT NULL,
              settlement_date     DATE NOT NULL,
              signal_date         DATE NOT NULL,
              config_revision     INTEGER NOT NULL,
              engine_mode         TEXT NOT NULL,
              code_hash           TEXT NOT NULL,
              state_hash          TEXT,
              data_release_id     TEXT,
              data_release_signature TEXT,
              data_version        TEXT,
              idempotency_key     TEXT NOT NULL,
              status              TEXT NOT NULL DEFAULT 'applied',
              cash_before         DOUBLE PRECISION NOT NULL,
              cash_after          DOUBLE PRECISION NOT NULL,
              positions_value     DOUBLE PRECISION NOT NULL,
              total_equity        DOUBLE PRECISION NOT NULL,
              commission          DOUBLE PRECISION NOT NULL DEFAULT 0,
              stamp_tax           DOUBLE PRECISION NOT NULL DEFAULT 0,
              warnings            JSONB NOT NULL DEFAULT '[]'::jsonb,
              response            JSONB NOT NULL,
              attempt_id          BIGINT,
              created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              rolled_back_at      TIMESTAMPTZ,
              CONSTRAINT paper_settlements_status_chk
                CHECK (status IN ('applied', 'rolled_back')),
              CONSTRAINT paper_settlements_account_fk
                FOREIGN KEY (user_id, account_id)
                REFERENCES paper_accounts (user_id, id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_settlement_applied_day "
            "ON paper_settlements (user_id, account_id, settlement_date) "
            "WHERE status = 'applied'"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_settlements_account_date "
            "ON paper_settlements (user_id, account_id, settlement_date DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_orders (
              id              BIGSERIAL PRIMARY KEY,
              user_id         BIGINT NOT NULL,
              account_id      BIGINT NOT NULL,
              settlement_id   BIGINT NOT NULL REFERENCES paper_settlements(id) ON DELETE CASCADE,
              order_id        TEXT NOT NULL,
              symbol          TEXT NOT NULL,
              side            TEXT,
              quantity        BIGINT,
              target_value    DOUBLE PRECISION,
              status          TEXT NOT NULL,
              reason_code     TEXT,
              submitted_at    TIMESTAMPTZ,
              UNIQUE (settlement_id, order_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_orders_account "
            "ON paper_orders (user_id, account_id, settlement_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_fills (
              id              BIGSERIAL PRIMARY KEY,
              user_id         BIGINT NOT NULL,
              account_id      BIGINT NOT NULL,
              settlement_id   BIGINT NOT NULL REFERENCES paper_settlements(id) ON DELETE CASCADE,
              order_id        TEXT NOT NULL,
              symbol          TEXT NOT NULL,
              side            TEXT NOT NULL,
              quantity        BIGINT NOT NULL,
              price           DOUBLE PRECISION NOT NULL,
              commission      DOUBLE PRECISION NOT NULL DEFAULT 0,
              stamp_tax       DOUBLE PRECISION NOT NULL DEFAULT 0,
              filled_at       TIMESTAMPTZ,
              UNIQUE (settlement_id, order_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_fills_account "
            "ON paper_fills (user_id, account_id, settlement_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_equity_daily (
              user_id         BIGINT NOT NULL,
              account_id      BIGINT NOT NULL,
              trade_date      DATE NOT NULL,
              settlement_id   BIGINT NOT NULL REFERENCES paper_settlements(id) ON DELETE CASCADE,
              cash            DOUBLE PRECISION NOT NULL,
              positions_value DOUBLE PRECISION NOT NULL,
              total_equity    DOUBLE PRECISION NOT NULL,
              daily_return    DOUBLE PRECISION,
              created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (user_id, account_id, trade_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_settlement_attempts (
              id                  BIGSERIAL PRIMARY KEY,
              user_id             BIGINT NOT NULL,
              account_id          BIGINT NOT NULL,
              settlement_date     DATE NOT NULL,
              attempt_no          INTEGER NOT NULL DEFAULT 1,
              trigger             TEXT NOT NULL DEFAULT 'manual',
              request             JSONB NOT NULL DEFAULT '{}'::jsonb,
              request_hash        TEXT NOT NULL DEFAULT '',
              http_status         INTEGER,
              error_code          TEXT,
              error_message       TEXT,
              response            JSONB,
              data_release_id     TEXT,
              data_release_signature TEXT,
              status              TEXT NOT NULL DEFAULT 'running',
              started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at         TIMESTAMPTZ,
              duration_ms         INTEGER,
              CONSTRAINT paper_attempts_status_chk
                CHECK (status IN ('running', 'settled', 'failed', 'skipped')),
              CONSTRAINT paper_attempts_account_fk
                FOREIGN KEY (user_id, account_id)
                REFERENCES paper_accounts (user_id, id) ON DELETE CASCADE
            )
            """
        )
        # 旧库补约束（CREATE TABLE IF NOT EXISTS 不会修改已存在的表）。
        conn.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'paper_attempts_account_fk'
              ) THEN
                ALTER TABLE paper_settlement_attempts
                  ADD CONSTRAINT paper_attempts_account_fk
                  FOREIGN KEY (user_id, account_id)
                  REFERENCES paper_accounts (user_id, id) ON DELETE CASCADE;
              END IF;
            END $$;
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_attempts_account "
            "ON paper_settlement_attempts (user_id, account_id, started_at DESC)"
        )


def _json(value: Any, *, default: Any = None) -> str:
    return json.dumps(
        value if value is not None else default,
        ensure_ascii=False,
        allow_nan=False,
    )


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def canonical_code_hash(strategy_code: str) -> str:
    return "sha256:" + hashlib.sha256(strategy_code.encode("utf-8")).hexdigest()


def infer_engine_mode(strategy_code: str) -> str:
    if "generate_signals" in strategy_code:
        return "vectorized"
    if "def initialize" in strategy_code:
        return "event"
    return "vectorized"


def _float_config(config: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(config.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def _int_config(config: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def resolve_project_snapshot(user_id: int, project_id: str) -> dict[str, Any]:
    """读取策略项目并生成账户快照。"""

    project = get_project(user_id, project_id)["project"]
    config = project.get("config") or {}
    if not isinstance(config, dict):
        config = {}
    strategy_id = str(config.get("strategy_id") or "").strip() or None
    code = str(config.get("strategy_code") or "").strip()
    builtin_mode: str | None = None
    builtin_name = ""
    if not code and strategy_id:
        builtin = get_builtin_strategy(strategy_id)
        code = str(builtin.get("strategy_code") or "").strip()
        builtin_mode = str(builtin.get("execution_mode") or "").strip().lower() or None
        builtin_name = str(builtin.get("name") or "")
    if not code:
        raise ValueError("策略项目没有可执行源码；内置策略请先在策略库同步源码快照")

    mode = str(config.get("engine_mode") or "").strip().lower()
    if mode not in {"event", "vectorized"}:
        mode = builtin_mode if builtin_mode in {"event", "vectorized"} else infer_engine_mode(code)
    if builtin_mode in {"event", "vectorized"} and builtin_mode != mode:
        raise ValueError(
            f"策略项目的执行模式 {mode} 与内置策略 {builtin_mode} 不一致"
        )

    return {
        "project_id": project_id,
        "project_name": str(project.get("name") or builtin_name or "未命名策略"),
        "strategy_id": strategy_id,
        "strategy_code": code,
        "code_hash": canonical_code_hash(code),
        "engine_mode": mode,
        "config_revision": 1,
        "universe": str(config.get("universe") or "CSI500"),
        "benchmark": str(config.get("benchmark") or "CSI300"),
        "commission_rate": _float_config(config, "commission_rate", DEFAULT_COMMISSION_RATE),
        "min_commission": _float_config(config, "min_commission", DEFAULT_MIN_COMMISSION),
        "stamp_tax": _float_config(config, "stamp_tax", DEFAULT_STAMP_TAX),
        "slippage_rate": _float_config(config, "slippage_rate", 0.0),
        "lot_size": _int_config(config, "lot_size", DEFAULT_LOT_SIZE),
        "filter_st": bool(config.get("filter_st", False)),
        "initial_cash": _float_config(config, "initial_capital", DEFAULT_INITIAL_CASH),
        "strategy_config": {
            "universe": str(config.get("universe") or "CSI500"),
            "benchmark": str(config.get("benchmark") or "CSI300"),
            "commission_rate": _float_config(config, "commission_rate", DEFAULT_COMMISSION_RATE),
            "min_commission": _float_config(config, "min_commission", DEFAULT_MIN_COMMISSION),
            "stamp_tax": _float_config(config, "stamp_tax", DEFAULT_STAMP_TAX),
            "slippage_rate": _float_config(config, "slippage_rate", 0.0),
            "lot_size": _int_config(config, "lot_size", DEFAULT_LOT_SIZE),
            "filter_st": bool(config.get("filter_st", False)),
        },
    }


def initial_next_settlement_date(
    now: datetime | None = None,
    *,
    requested: date | None = None,
) -> date:
    """创建账户时的首个结算日。

    - 显式传入 ``requested`` 时直接使用（允许补历史联调，但不能晚于今天）。
    - 交易日收盘前创建：当天可结算；收盘后或非工作日创建：下一个工作日。
    """

    today = (now or datetime.now()).date()
    if requested is not None:
        if requested > today:
            raise ValueError("首个结算日不能晚于今天")
        return requested
    current = now or datetime.now()
    if current.weekday() < 5 and current.time() < MARKET_CLOSE:
        return today
    candidate = today + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def create_account(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("strategy_project_id") or payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("strategy_project_id 不能为空")
    snapshot = resolve_project_snapshot(user_id, project_id)
    name = str(payload.get("name") or snapshot["project_name"]).strip() or snapshot["project_name"]
    try:
        initial_cash = float(payload.get("initial_cash", snapshot["initial_cash"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("初始资金必须是数字") from exc
    if initial_cash <= 0:
        raise ValueError("初始资金必须大于 0")

    requested = payload.get("first_settlement_date")
    first = None
    if requested:
        try:
            first = date.fromisoformat(str(requested))
        except ValueError as exc:
            raise ValueError("first_settlement_date 必须是 YYYY-MM-DD") from exc
    first = first or initial_next_settlement_date()
    next_date = initial_next_settlement_date(requested=first)

    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO paper_accounts
              (user_id, name, project_id, project_name, engine_mode, strategy_id,
               strategy_code, code_hash, strategy_config, config_revision,
               universe, benchmark, commission_rate, min_commission, stamp_tax,
               slippage_rate, lot_size, filter_st, initial_cash, cash, total_equity,
               first_settlement_date, next_settlement_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                user_id,
                name,
                snapshot["project_id"],
                snapshot["project_name"],
                snapshot["engine_mode"],
                snapshot["strategy_id"],
                snapshot["strategy_code"],
                snapshot["code_hash"],
                _json(snapshot["strategy_config"]),
                snapshot["config_revision"],
                snapshot["universe"],
                snapshot["benchmark"],
                snapshot["commission_rate"],
                snapshot["min_commission"],
                snapshot["stamp_tax"],
                snapshot["slippage_rate"],
                snapshot["lot_size"],
                snapshot["filter_st"],
                initial_cash,
                initial_cash,
                initial_cash,
                first,
                next_date,
            ),
        ).fetchone()
    return _account_row(dict(row))


def _account_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "userId": int(row["user_id"]),
        "name": row["name"],
        "projectId": row["project_id"],
        "projectName": row.get("project_name") or "",
        "engineMode": row["engine_mode"],
        "strategyId": row.get("strategy_id"),
        "codeHash": row["code_hash"],
        "configRevision": int(row.get("config_revision") or 1),
        "universe": row["universe"],
        "benchmark": row["benchmark"],
        "commissionRate": float(row["commission_rate"]),
        "minCommission": float(row["min_commission"]),
        "stampTax": float(row["stamp_tax"]),
        "slippageRate": float(row["slippage_rate"]),
        "lotSize": int(row["lot_size"]),
        "filterSt": bool(row["filter_st"]),
        "initialCash": float(row["initial_cash"]),
        "cash": float(row["cash"]),
        "totalEquity": float(row["total_equity"]),
        "positionsValue": float(row["positions_value"]),
        "firstSettlementDate": _iso(row.get("first_settlement_date")),
        "nextSettlementDate": _iso(row.get("next_settlement_date")),
        "lastSettledDate": _iso(row.get("last_settled_date")),
        "status": row["status"],
        "lastErrorCode": row.get("last_error_code"),
        "lastErrorMessage": row.get("last_error_message"),
        "retryCount": int(row.get("retry_count") or 0),
        "nextRetryAt": _iso(row.get("next_retry_at")),
        "createdAt": _iso(row.get("created_at")),
        "updatedAt": _iso(row.get("updated_at")),
    }


def list_accounts(user_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_accounts WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return {"ok": True, "accounts": [_account_row(dict(row)) for row in rows]}


def get_account_row(user_id: int, account_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM paper_accounts WHERE user_id = %s AND id = %s",
            (user_id, account_id),
        ).fetchone()
    if not row:
        raise KeyError(account_id)
    return dict(row)


def get_account(user_id: int, account_id: int) -> dict[str, Any]:
    row = get_account_row(user_id, account_id)
    return {
        "ok": True,
        "account": _account_row(row),
        "positions": list_positions(user_id, account_id),
        "latestSettlement": _latest_settlement(user_id, account_id),
    }


def update_account(user_id: int, account_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    fields: list[str] = []
    values: list[Any] = []
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("账户名称不能为空")
        fields.append("name = %s")
        values.append(name)
    if "status" in payload:
        status = str(payload.get("status") or "").strip()
        if status not in {"active", "paused", "closed"}:
            raise ValueError("status 仅支持 active / paused / closed")
        fields.append("status = %s")
        values.append(status)
        if status == "active":
            fields.append("last_error_code = NULL")
            fields.append("last_error_message = NULL")
            fields.append("retry_count = 0")
            fields.append("next_retry_at = NULL")
    if not fields:
        raise ValueError("没有可更新的字段")
    values.extend([user_id, account_id])
    with get_conn() as conn:
        row = conn.execute(
            f"UPDATE paper_accounts SET {', '.join(fields)}, updated_at = NOW() "
            "WHERE user_id = %s AND id = %s RETURNING *",
            tuple(values),
        ).fetchone()
    if not row:
        raise KeyError(account_id)
    return _account_row(dict(row))


def list_positions(user_id: int, account_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT symbol, quantity, available_quantity, average_cost,
                   mark_price, market_value, updated_at
            FROM paper_positions
            WHERE user_id = %s AND account_id = %s
            ORDER BY symbol
            """,
            (user_id, account_id),
        ).fetchall()
    return [
        {
            "symbol": row["symbol"],
            "quantity": int(row["quantity"]),
            "availableQuantity": int(row["available_quantity"]),
            "averageCost": float(row["average_cost"]),
            "markPrice": (float(row["mark_price"]) if row.get("mark_price") is not None else None),
            "marketValue": (float(row["market_value"]) if row.get("market_value") is not None else None),
            "updatedAt": _iso(row.get("updated_at")),
        }
        for row in rows
    ]


def _latest_settlement(user_id: int, account_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM paper_settlements
            WHERE user_id = %s AND account_id = %s
            ORDER BY settlement_date DESC, id DESC LIMIT 1
            """,
            (user_id, account_id),
        ).fetchone()
    return _settlement_row(dict(row)) if row else None


def _next_account_view(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    return {
        "cash": float(raw.get("cash") or 0),
        "positionsValue": float(raw.get("positions_value") or 0),
        "totalEquity": float(raw.get("total_equity") or 0),
        "positions": [
            {
                "symbol": item.get("symbol"),
                "quantity": int(item.get("quantity") or 0),
                "availableQuantity": int(item.get("available_quantity") or 0),
                "averageCost": float(item.get("average_cost") or 0),
                "markPrice": (
                    float(item["mark_price"])
                    if item.get("mark_price") is not None
                    else None
                ),
                "marketValue": (
                    float(item["market_value"])
                    if item.get("market_value") is not None
                    else None
                ),
            }
            for item in raw.get("positions") or []
        ],
    }


def _settlement_row(row: dict[str, Any]) -> dict[str, Any]:
    response = row.get("response") or {}
    next_account = _next_account_view(response.get("next_account"))
    return {
        "id": int(row["id"]),
        "settlementDate": _iso(row.get("settlement_date")),
        "signalDate": _iso(row.get("signal_date")),
        "status": row.get("status"),
        "engineMode": row.get("engine_mode"),
        "configRevision": int(row.get("config_revision") or 1),
        "dataReleaseId": row.get("data_release_id"),
        "dataReleaseSignature": row.get("data_release_signature"),
        "codeHash": row.get("code_hash"),
        "stateHash": row.get("state_hash"),
        "cashBefore": float(row.get("cash_before") or 0),
        "cashAfter": float(row.get("cash_after") or 0),
        "positionsValue": float(row.get("positions_value") or 0),
        "totalEquity": float(row.get("total_equity") or 0),
        "commission": float(row.get("commission") or 0),
        "stampTax": float(row.get("stamp_tax") or 0),
        "warnings": row.get("warnings") or [],
        "nextAccount": next_account,
        "createdAt": _iso(row.get("created_at")),
        "rolledBackAt": _iso(row.get("rolled_back_at")),
    }


def list_settlements(
    user_id: int, account_id: int, *, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total = conn.execute(
            "SELECT count(*) AS n FROM paper_settlements WHERE user_id = %s AND account_id = %s",
            (user_id, account_id),
        ).fetchone()["n"]
        rows = conn.execute(
            """
            SELECT * FROM paper_settlements
            WHERE user_id = %s AND account_id = %s
            ORDER BY settlement_date DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, account_id, limit, offset),
        ).fetchall()
    return {
        "ok": True,
        "total": int(total),
        "settlements": [_settlement_row(dict(row)) for row in rows],
    }


def _ledger_rows(
    table: str, user_id: int, account_id: int, *, start: str | None, end: str | None, limit: int, offset: int
) -> dict[str, Any]:
    clauses = ["t.user_id = %s", "t.account_id = %s", "s.status = 'applied'"]
    params: list[Any] = [user_id, account_id]
    if start:
        clauses.append("s.settlement_date >= %s")
        params.append(start)
    if end:
        clauses.append("s.settlement_date <= %s")
        params.append(end)
    where = " AND ".join(clauses)
    limit = max(1, min(500, int(limit)))
    offset = max(0, int(offset))
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM {table} t "
            f"JOIN paper_settlements s ON s.id = t.settlement_id WHERE {where}",
            tuple(params),
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT t.*, s.settlement_date FROM {table} t "
            f"JOIN paper_settlements s ON s.id = t.settlement_id "
            f"WHERE {where} ORDER BY s.settlement_date DESC, t.id ASC "
            "LIMIT %s OFFSET %s",
            tuple(params + [limit, offset]),
        ).fetchall()
    return {"ok": True, "total": int(total), "rows": [dict(row) for row in rows]}


def list_orders(
    user_id: int,
    account_id: int,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    data = _ledger_rows(
        "paper_orders", user_id, account_id, start=start, end=end, limit=limit, offset=offset
    )
    data["orders"] = [
        {
            "orderId": row["order_id"],
            "settlementDate": _iso(row["settlement_date"]),
            "symbol": row["symbol"],
            "side": row.get("side"),
            "quantity": int(row["quantity"]) if row.get("quantity") is not None else None,
            "targetValue": row.get("target_value"),
            "status": row["status"],
            "reasonCode": row.get("reason_code"),
            "submittedAt": _iso(row.get("submitted_at")),
        }
        for row in data.pop("rows")
    ]
    return data


def list_fills(
    user_id: int,
    account_id: int,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    data = _ledger_rows(
        "paper_fills", user_id, account_id, start=start, end=end, limit=limit, offset=offset
    )
    data["fills"] = [
        {
            "orderId": row["order_id"],
            "settlementDate": _iso(row["settlement_date"]),
            "symbol": row["symbol"],
            "side": row["side"],
            "quantity": int(row["quantity"]),
            "price": float(row["price"]),
            "commission": float(row["commission"]),
            "stampTax": float(row["stamp_tax"]),
            "filledAt": _iso(row.get("filled_at")),
        }
        for row in data.pop("rows")
    ]
    return data


def list_equity(
    user_id: int, account_id: int, *, start: str | None = None, end: str | None = None
) -> dict[str, Any]:
    clauses = ["user_id = %s", "account_id = %s"]
    params: list[Any] = [user_id, account_id]
    if start:
        clauses.append("trade_date >= %s")
        params.append(start)
    if end:
        clauses.append("trade_date <= %s")
        params.append(end)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM paper_equity_daily WHERE {' AND '.join(clauses)} "
            "ORDER BY trade_date",
            tuple(params),
        ).fetchall()
    return {
        "ok": True,
        "equity": [
            {
                "date": _iso(row["trade_date"]),
                "cash": float(row["cash"]),
                "positionsValue": float(row["positions_value"]),
                "totalEquity": float(row["total_equity"]),
                "dailyReturn": (
                    float(row["daily_return"]) if row.get("daily_return") is not None else None
                ),
            }
            for row in rows
        ],
    }


def list_attempts(user_id: int, account_id: int, *, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(200, int(limit)))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, settlement_date, attempt_no, trigger, http_status, error_code,
                   error_message, data_release_id, status, started_at, finished_at, duration_ms
            FROM paper_settlement_attempts
            WHERE user_id = %s AND account_id = %s
            ORDER BY started_at DESC LIMIT %s
            """,
            (user_id, account_id, limit),
        ).fetchall()
    return {
        "ok": True,
        "attempts": [
            {
                "id": int(row["id"]),
                "settlementDate": _iso(row["settlement_date"]),
                "attemptNo": int(row["attempt_no"]),
                "trigger": row["trigger"],
                "httpStatus": row.get("http_status"),
                "errorCode": row.get("error_code"),
                "errorMessage": row.get("error_message"),
                "dataReleaseId": row.get("data_release_id"),
                "status": row["status"],
                "startedAt": _iso(row.get("started_at")),
                "finishedAt": _iso(row.get("finished_at")),
                "durationMs": row.get("duration_ms"),
            }
            for row in rows
        ],
    }


# ---------------- 结算写入 ----------------


def start_attempt(
    user_id: int,
    account_id: int,
    *,
    settlement_date: date,
    trigger: str,
    request_payload: dict[str, Any],
) -> int:
    request_json = _json(request_payload, default={})
    request_hash = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
    with get_conn() as conn:
        previous = conn.execute(
            "SELECT coalesce(max(attempt_no), 0) AS n FROM paper_settlement_attempts "
            "WHERE user_id = %s AND account_id = %s AND settlement_date = %s",
            (user_id, account_id, settlement_date),
        ).fetchone()["n"]
        row = conn.execute(
            """
            INSERT INTO paper_settlement_attempts
              (user_id, account_id, settlement_date, attempt_no, trigger,
               request, request_hash, status)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, 'running')
            RETURNING id
            """,
            (
                user_id,
                account_id,
                settlement_date,
                int(previous) + 1,
                trigger,
                request_json,
                request_hash,
            ),
        ).fetchone()
    return int(row["id"])


def finish_attempt(
    attempt_id: int,
    *,
    status: str,
    http_status: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    response: dict[str, Any] | None = None,
    data_release_id: str | None = None,
    data_release_signature: str | None = None,
    duration_ms: int | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE paper_settlement_attempts
            SET status = %s, http_status = %s, error_code = %s, error_message = %s,
                response = %s::jsonb, data_release_id = %s,
                data_release_signature = %s, duration_ms = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (
                status,
                http_status,
                error_code,
                error_message,
                _json(response) if response is not None else None,
                data_release_id,
                data_release_signature,
                duration_ms,
                attempt_id,
            ),
        )


def mark_account_error(
    user_id: int,
    account_id: int,
    *,
    code: str,
    message: str,
    blocked: bool,
    retry_delay_sec: int | None = None,
) -> None:
    with get_conn() as conn:
        if blocked:
            conn.execute(
                "UPDATE paper_accounts SET status = 'blocked', last_error_code = %s, "
                "last_error_message = %s, updated_at = NOW() "
                "WHERE user_id = %s AND id = %s",
                (code, message, user_id, account_id),
            )
            return
        retry_at = (
            datetime.now() + timedelta(seconds=retry_delay_sec)
            if retry_delay_sec
            else None
        )
        conn.execute(
            "UPDATE paper_accounts SET last_error_code = %s, last_error_message = %s, "
            "retry_count = retry_count + 1, next_retry_at = %s, updated_at = NOW() "
            "WHERE user_id = %s AND id = %s",
            (code, message, retry_at, user_id, account_id),
        )


def advance_next_settlement_date(
    user_id: int, account_id: int, next_date: date
) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE paper_accounts SET next_settlement_date = %s, "
            "last_error_code = NULL, last_error_message = NULL, "
            "retry_count = 0, next_retry_at = NULL, updated_at = NOW() "
            "WHERE user_id = %s AND id = %s",
            (next_date, user_id, account_id),
        )


def claim_settlement_lease(
    user_id: int, account_id: int, *, owner: str, ttl_sec: int
) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE paper_accounts
            SET settle_lease_owner = %s,
                settle_lease_until = NOW() + make_interval(secs => %s)
            WHERE user_id = %s AND id = %s AND status = 'active'
              AND (settle_lease_until IS NULL OR settle_lease_until < NOW())
            RETURNING id
            """,
            (owner, max(30, int(ttl_sec)), user_id, account_id),
        ).fetchone()
    return bool(row)


def release_settlement_lease(user_id: int, account_id: int, owner: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE paper_accounts SET settle_lease_owner = NULL, "
            "settle_lease_until = NULL "
            "WHERE user_id = %s AND id = %s AND settle_lease_owner = %s",
            (user_id, account_id, owner),
        )


def find_applied_settlement(
    user_id: int, account_id: int, settlement_date: date
) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM paper_settlements WHERE user_id = %s AND account_id = %s "
            "AND settlement_date = %s AND status = 'applied'",
            (user_id, account_id, settlement_date),
        ).fetchone()
    return _settlement_row(dict(row)) if row else None


def apply_settlement(
    user_id: int,
    account_id: int,
    *,
    response: dict[str, Any],
    attempt_id: int | None = None,
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把一次 RE 结算结果原子写入账户账本。"""

    settlement_date = date.fromisoformat(str(response["settlement_date"]))
    signal_date = date.fromisoformat(str(response["signal_date"]))
    next_account = response.get("next_account") or {}
    positions = next_account.get("positions") or []
    fees = response.get("fees") or {}
    release_id = response.get("data_release_id")
    release_signature = response.get("data_release_signature")
    state_payload = response.get("strategy_state") or None
    state_hash = response.get("state_hash")
    code_hash = str(response.get("code_hash") or "")

    with get_conn() as conn:
        account = conn.execute(
            "SELECT * FROM paper_accounts WHERE user_id = %s AND id = %s FOR UPDATE",
            (user_id, account_id),
        ).fetchone()
        if not account:
            raise KeyError(account_id)
        account = dict(account)
        if account["status"] != "active":
            raise PermissionError("账户不是 active 状态，不能结算")
        expected_revision = (request_meta or {}).get("config_revision")
        if expected_revision is not None and int(account["config_revision"]) != int(expected_revision):
            raise ValueError(
                "账户策略配置在结算期间发生变化，请重试"
            )
        existing = conn.execute(
            "SELECT * FROM paper_settlements WHERE user_id = %s AND account_id = %s "
            "AND settlement_date = %s AND status = 'applied'",
            (user_id, account_id, settlement_date),
        ).fetchone()
        if existing:
            return {"idempotent": True, "settlement": _settlement_row(dict(existing))}

        next_settlement = account.get("next_settlement_date")
        if next_settlement is not None:
            next_date = next_settlement
            if isinstance(next_date, datetime):
                next_date = next_date.date()
            if next_date != settlement_date:
                raise ValueError(
                    f"结算日不连续：期望 {next_date.isoformat()}，收到 {settlement_date.isoformat()}"
                )

        idempotency_key = hashlib.sha256(
            "|".join(
                [
                    str(account_id),
                    settlement_date.isoformat(),
                    str(account.get("config_revision") or 1),
                    str(release_id or ""),
                ]
            ).encode("utf-8")
        ).hexdigest()
        settlement_row = conn.execute(
            """
            INSERT INTO paper_settlements
              (user_id, account_id, settlement_date, signal_date, config_revision,
               engine_mode, code_hash, state_hash, data_release_id,
               data_release_signature, data_version, idempotency_key, status,
               cash_before, cash_after, positions_value, total_equity,
               commission, stamp_tax, warnings, response, attempt_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'applied',
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            RETURNING *
            """,
            (
                user_id,
                account_id,
                settlement_date,
                signal_date,
                int(account.get("config_revision") or 1),
                response.get("engine_mode") or account["engine_mode"],
                code_hash,
                state_hash,
                release_id,
                release_signature,
                response.get("data_version") or release_id,
                idempotency_key,
                float(account["cash"]),
                float(next_account.get("cash") or 0),
                float(next_account.get("positions_value") or 0),
                float(next_account.get("total_equity") or 0),
                float(fees.get("commission") or 0),
                float(fees.get("stamp_tax") or 0),
                _json(response.get("warnings") or [], default=[]),
                _json(response, default={}),
                attempt_id,
            ),
        ).fetchone()
        settlement_id = int(settlement_row["id"])

        for order in response.get("orders") or []:
            conn.execute(
                """
                INSERT INTO paper_orders
                  (user_id, account_id, settlement_id, order_id, symbol, side,
                   quantity, target_value, status, reason_code, submitted_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (settlement_id, order_id) DO NOTHING
                """,
                (
                    user_id,
                    account_id,
                    settlement_id,
                    str(order.get("order_id") or ""),
                    str(order.get("symbol") or ""),
                    order.get("side"),
                    order.get("quantity"),
                    order.get("target_value"),
                    str(order.get("status") or ""),
                    order.get("reason_code"),
                    order.get("submitted_at"),
                ),
            )
        for fill in response.get("fills") or []:
            conn.execute(
                """
                INSERT INTO paper_fills
                  (user_id, account_id, settlement_id, order_id, symbol, side,
                   quantity, price, commission, stamp_tax, filled_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (settlement_id, order_id) DO NOTHING
                """,
                (
                    user_id,
                    account_id,
                    settlement_id,
                    str(fill.get("order_id") or ""),
                    str(fill.get("symbol") or ""),
                    str(fill.get("side") or ""),
                    int(fill.get("quantity") or 0),
                    float(fill.get("price") or 0),
                    float(fill.get("commission") or 0),
                    float(fill.get("stamp_tax") or 0),
                    fill.get("timestamp"),
                ),
            )

        conn.execute(
            "DELETE FROM paper_positions WHERE user_id = %s AND account_id = %s",
            (user_id, account_id),
        )
        for item in positions:
            quantity = int(item.get("quantity") or 0)
            if quantity <= 0:
                continue
            cost = float(item.get("average_cost") or 0)
            mark = item.get("mark_price")
            market_value = item.get("market_value")
            conn.execute(
                """
                INSERT INTO paper_positions
                  (user_id, account_id, symbol, quantity, available_quantity,
                   average_cost, mark_price, market_value)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    account_id,
                    str(item.get("symbol") or ""),
                    quantity,
                    int(item.get("available_quantity") or 0),
                    cost,
                    float(mark) if mark is not None else None,
                    float(market_value) if market_value is not None else None,
                ),
            )

        previous_equity = conn.execute(
            "SELECT total_equity FROM paper_equity_daily WHERE user_id = %s AND account_id = %s "
            "ORDER BY trade_date DESC LIMIT 1",
            (user_id, account_id),
        ).fetchone()
        previous_total = float(previous_equity["total_equity"]) if previous_equity else None
        total_equity = float(next_account.get("total_equity") or 0)
        daily_return = (
            (total_equity / previous_total - 1.0)
            if previous_total and previous_total > 0
            else None
        )
        conn.execute(
            """
            INSERT INTO paper_equity_daily
              (user_id, account_id, trade_date, settlement_id, cash,
               positions_value, total_equity, daily_return)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, account_id, trade_date) DO UPDATE
            SET settlement_id = EXCLUDED.settlement_id,
                cash = EXCLUDED.cash,
                positions_value = EXCLUDED.positions_value,
                total_equity = EXCLUDED.total_equity,
                daily_return = EXCLUDED.daily_return
            """,
            (
                user_id,
                account_id,
                settlement_date,
                settlement_id,
                float(next_account.get("cash") or 0),
                float(next_account.get("positions_value") or 0),
                total_equity,
                daily_return,
            ),
        )

        next_trading_day = response.get("next_trading_day")
        if next_trading_day:
            following = date.fromisoformat(str(next_trading_day))
        else:
            following = settlement_date + timedelta(days=1)
            while following.weekday() >= 5:
                following += timedelta(days=1)
        conn.execute(
            """
            UPDATE paper_accounts
            SET cash = %s, total_equity = %s, positions_value = %s,
                strategy_state = %s::jsonb, state_hash = %s,
                last_settled_date = %s, next_settlement_date = %s,
                config_revision = %s,
                last_settlement_release_id = %s,
                last_settlement_release_signature = %s,
                last_error_code = NULL, last_error_message = NULL,
                retry_count = 0, next_retry_at = NULL,
                settle_lease_owner = NULL, settle_lease_until = NULL,
                updated_at = NOW()
            WHERE user_id = %s AND id = %s
            """,
            (
                float(next_account.get("cash") or 0),
                total_equity,
                float(next_account.get("positions_value") or 0),
                _json(state_payload) if state_payload else None,
                state_hash,
                settlement_date,
                following,
                int(account.get("config_revision") or 1),
                release_id,
                release_signature,
                user_id,
                account_id,
            ),
        )
        if attempt_id is not None:
            conn.execute(
                "UPDATE paper_settlement_attempts SET status = 'settled', "
                "http_status = 200, response = %s::jsonb, finished_at = NOW(), "
                "data_release_id = %s, data_release_signature = %s "
                "WHERE id = %s",
                (_json(response), release_id, release_signature, attempt_id),
            )
    return {"idempotent": False, "settlement": _settlement_row(dict(settlement_row))}


def rollback_latest_settlement(user_id: int, account_id: int) -> dict[str, Any]:
    """回滚最新一笔 applied 结算，并恢复上一日状态。"""

    with get_conn() as conn:
        latest = conn.execute(
            "SELECT * FROM paper_settlements WHERE user_id = %s AND account_id = %s "
            "AND status = 'applied' ORDER BY settlement_date DESC, id DESC LIMIT 1 FOR UPDATE",
            (user_id, account_id),
        ).fetchone()
        if not latest:
            raise KeyError("no settlement")
        latest = dict(latest)
        previous = conn.execute(
            "SELECT * FROM paper_settlements WHERE user_id = %s AND account_id = %s "
            "AND status = 'applied' AND settlement_date < %s "
            "ORDER BY settlement_date DESC, id DESC LIMIT 1",
            (user_id, account_id, latest["settlement_date"]),
        ).fetchone()
        account = conn.execute(
            "SELECT * FROM paper_accounts WHERE user_id = %s AND id = %s FOR UPDATE",
            (user_id, account_id),
        ).fetchone()
        if not account:
            raise KeyError(account_id)
        account = dict(account)
        previous_response = (dict(previous).get("response") if previous else None) or {}
        next_account = previous_response.get("next_account") or {}
        previous_state = previous_response.get("strategy_state") or None
        previous_hash = dict(previous).get("state_hash") if previous else None
        previous_date = dict(previous).get("settlement_date") if previous else None
        previous_release = dict(previous).get("data_release_id") if previous else None
        previous_signature = (
            dict(previous).get("data_release_signature") if previous else None
        )
        cash = float(next_account.get("cash", account["initial_cash"]))
        total_equity = float(next_account.get("total_equity", account["initial_cash"]))
        positions_value = float(next_account.get("positions_value", 0))

        conn.execute(
            "UPDATE paper_settlements SET status = 'rolled_back', rolled_back_at = NOW() "
            "WHERE id = %s",
            (int(latest["id"]),),
        )
        conn.execute(
            "DELETE FROM paper_equity_daily WHERE user_id = %s AND account_id = %s AND trade_date = %s",
            (user_id, account_id, latest["settlement_date"]),
        )
        conn.execute(
            "DELETE FROM paper_positions WHERE user_id = %s AND account_id = %s",
            (user_id, account_id),
        )
        for item in next_account.get("positions") or []:
            quantity = int(item.get("quantity") or 0)
            if quantity <= 0:
                continue
            cost = float(item.get("average_cost") or 0)
            mark = item.get("mark_price")
            market_value = item.get("market_value")
            conn.execute(
                """
                INSERT INTO paper_positions
                  (user_id, account_id, symbol, quantity, available_quantity,
                   average_cost, mark_price, market_value)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    account_id,
                    str(item.get("symbol") or ""),
                    quantity,
                    int(item.get("available_quantity") or 0),
                    cost,
                    float(mark) if mark is not None else None,
                    float(market_value) if market_value is not None else None,
                ),
            )
        conn.execute(
            """
            UPDATE paper_accounts
            SET cash = %s, total_equity = %s, positions_value = %s,
                strategy_state = %s::jsonb, state_hash = %s,
                last_settled_date = %s, next_settlement_date = %s,
                last_settlement_release_id = %s,
                last_settlement_release_signature = %s,
                last_error_code = NULL, last_error_message = NULL,
                retry_count = 0, next_retry_at = NULL, updated_at = NOW()
            WHERE user_id = %s AND id = %s
            """,
            (
                cash,
                total_equity,
                positions_value,
                _json(previous_state) if previous_state else None,
                previous_hash,
                previous_date,
                latest["settlement_date"],
                previous_release,
                previous_signature,
                user_id,
                account_id,
            ),
        )
    return {
        "ok": True,
        "rolledBackSettlementId": int(latest["id"]),
        "account": get_account(user_id, account_id)["account"],
    }


def sync_strategy_from_project(user_id: int, account_id: int) -> dict[str, Any]:
    """把策略项目的最新源码/参数同步到账户（revision + 1）。"""

    row = get_account_row(user_id, account_id)
    snapshot = resolve_project_snapshot(user_id, row["project_id"])
    code_changed = snapshot["code_hash"] != row["code_hash"]
    with get_conn() as conn:
        updated = conn.execute(
            """
            UPDATE paper_accounts
            SET project_name = %s, engine_mode = %s, strategy_id = %s,
                strategy_code = %s, code_hash = %s,
                strategy_config = %s::jsonb,
                config_revision = config_revision + 1,
                universe = %s, benchmark = %s,
                commission_rate = %s, min_commission = %s, stamp_tax = %s,
                slippage_rate = %s, lot_size = %s, filter_st = %s,
                strategy_state = CASE WHEN %s THEN NULL ELSE strategy_state END,
                state_hash = CASE WHEN %s THEN NULL ELSE state_hash END,
                updated_at = NOW()
            WHERE user_id = %s AND id = %s RETURNING *
            """,
            (
                snapshot["project_name"],
                snapshot["engine_mode"],
                snapshot["strategy_id"],
                snapshot["strategy_code"],
                snapshot["code_hash"],
                _json(snapshot["strategy_config"]),
                snapshot["universe"],
                snapshot["benchmark"],
                snapshot["commission_rate"],
                snapshot["min_commission"],
                snapshot["stamp_tax"],
                snapshot["slippage_rate"],
                snapshot["lot_size"],
                snapshot["filter_st"],
                code_changed,
                code_changed,
                user_id,
                account_id,
            ),
        ).fetchone()
    if not updated:
        raise KeyError(account_id)
    return {
        "ok": True,
        "codeChanged": code_changed,
        "account": _account_row(dict(updated)),
    }


def list_due_accounts(latest_ready: date, *, limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM paper_accounts
            WHERE status = 'active'
              AND next_settlement_date <= %s
              AND (next_retry_at IS NULL OR next_retry_at <= NOW())
              AND (settle_lease_until IS NULL OR settle_lease_until < NOW())
            ORDER BY next_settlement_date ASC, id ASC
            LIMIT %s
            """,
            (latest_ready, max(1, min(200, int(limit)))),
        ).fetchall()
    return [dict(row) for row in rows]


def active_accounts_count() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM paper_accounts WHERE status = 'active'"
        ).fetchone()
    return int(row["n"])
