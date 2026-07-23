# -*- coding: utf-8 -*-
"""策略研究项目 / 回测记录：按 user_id 隔离，存 Postgres。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from services.db import get_conn

DEFAULT_STRATEGY_CODE = '''from quantcore import (
    EqualWeight,
    EveryNTradingDays,
    FactorPortfolioStrategy,
    TopN,
    factor,
    signal,
)

# --- SVQUANT_PARAMS (与左侧表单同步，请求以表单为准) ---
UNIVERSE = "CSI500"
BENCHMARK = "CSI300"
COMMISSION_RATE = 0.0003
STAMP_TAX = 0.001
SLIPPAGE_RATE = 0.001
INITIAL_CAPITAL = 1_000_000
TOP_N = 30
REBALANCE_DAYS = 20
# --- SVQUANT_PARAMS_END ---


class DemoMomentumStrategy(FactorPortfolioStrategy):
    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    @factor
    def momentum_20d(self):
        return self.close.pct_change(20)

    @signal
    def score(self):
        return self.rank(self.momentum_20d())
'''


def ensure_strategy_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_projects (
              id            TEXT NOT NULL,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name          TEXT NOT NULL,
              description   TEXT NOT NULL DEFAULT '',
              config        JSONB NOT NULL DEFAULT '{}'::jsonb,
              run_count     INTEGER NOT NULL DEFAULT 0,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (user_id, id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_strategy_projects_user_updated "
            "ON strategy_projects (user_id, updated_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_runs (
              id            TEXT NOT NULL,
              user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              project_id    TEXT NOT NULL,
              name          TEXT NOT NULL DEFAULT '',
              description   TEXT NOT NULL DEFAULT '',
              request       JSONB NOT NULL DEFAULT '{}'::jsonb,
              result        JSONB NOT NULL DEFAULT '{}'::jsonb,
              finished_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              elapsed_sec   DOUBLE PRECISION NOT NULL DEFAULT 0,
              PRIMARY KEY (user_id, id),
              CONSTRAINT strategy_runs_project_fk
                FOREIGN KEY (user_id, project_id)
                REFERENCES strategy_projects (user_id, id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_strategy_runs_project "
            "ON strategy_runs (user_id, project_id, finished_at DESC)"
        )


def _iso(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.isoformat()
    return val


def _default_config() -> dict[str, Any]:
    return {
        "universe": "CSI500",
        "benchmark": "CSI300",
        "rangeMode": "period",
        "backtestPeriod": "10y",
        "startDate": "2016-01-01",
        "endDate": "2026-01-01",
        "commission_rate": 0.0003,
        "stamp_tax": 0.001,
        "slippage_rate": 0.001,
        "initial_capital": 1_000_000,
        "top_n": 30,
        "rebalance_days": 20,
        "strategy_code": DEFAULT_STRATEGY_CODE,
    }


def _row_project(row: dict[str, Any]) -> dict[str, Any]:
    cfg = row.get("config") or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description") or "",
        "createdAt": _iso(row.get("created_at")),
        "updatedAt": _iso(row.get("updated_at")),
        "runCount": int(row.get("run_count") or 0),
        "config": cfg,
    }


def _row_run(row: dict[str, Any]) -> dict[str, Any]:
    req = row.get("request") or {}
    res = row.get("result") or {}
    if isinstance(req, str):
        req = json.loads(req)
    if isinstance(res, str):
        res = json.loads(res)
    return {
        "id": row["id"],
        "projectId": row["project_id"],
        "name": row.get("name") or "",
        "description": row.get("description") or "",
        "request": req,
        "result": res,
        "finishedAt": _iso(row.get("finished_at")),
        "elapsedSec": float(row.get("elapsed_sec") or 0),
    }


def list_projects(user_id: int, *, visible_only: bool = False) -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM strategy_projects
            WHERE user_id = %s
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        uname = conn.execute(
            "SELECT username FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    projects = [_row_project(dict(r)) for r in rows]
    if visible_only:
        projects = [p for p in projects if (p.get("runCount") or 0) > 0]
    return {
        "ok": True,
        "user_id": int(user_id),
        "username": (uname["username"] if uname else None),
        "projects": projects,
    }


def get_project(user_id: int, project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        ).fetchone()
    if not row:
        raise KeyError(project_id)
    return {"ok": True, "user_id": int(user_id), "project": _row_project(dict(row))}


def upsert_project(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    pid = str(payload.get("id") or "").strip() or str(uuid.uuid4())
    name = str(payload.get("name") or payload.get("description") or "未命名策略").strip()
    description = str(payload.get("description") or name).strip()
    config = payload.get("config") or _default_config()
    if not isinstance(config, dict):
        config = _default_config()
    if not str(config.get("strategy_code") or "").strip():
        config = {**config, "strategy_code": DEFAULT_STRATEGY_CODE}

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM strategy_projects WHERE user_id = %s AND id = %s",
            (user_id, pid),
        ).fetchone()
        if existing:
            row = conn.execute(
                """
                UPDATE strategy_projects
                SET name = %s, description = %s, config = %s::jsonb, updated_at = NOW()
                WHERE user_id = %s AND id = %s
                RETURNING *
                """,
                (
                    name,
                    description,
                    json.dumps(config, ensure_ascii=False),
                    user_id,
                    pid,
                ),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO strategy_projects
                  (id, user_id, name, description, config, run_count)
                VALUES (%s, %s, %s, %s, %s::jsonb, 0)
                RETURNING *
                """,
                (
                    pid,
                    user_id,
                    name,
                    description,
                    json.dumps(config, ensure_ascii=False),
                ),
            ).fetchone()
    return {"ok": True, "user_id": int(user_id), "project": _row_project(dict(row))}


def create_project(
    user_id: int,
    *,
    name: str,
    description: str | None = None,
) -> dict[str, Any]:
    title = (name or description or "未命名策略").strip()
    return upsert_project(
        user_id,
        {
            "id": str(uuid.uuid4()),
            "name": title,
            "description": (description or title).strip(),
            "config": _default_config(),
        },
    )


def delete_project(user_id: int, project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "DELETE FROM strategy_projects WHERE user_id = %s AND id = %s RETURNING id",
            (user_id, project_id),
        ).fetchone()
        if not row:
            raise KeyError(project_id)
    return {"ok": True, "id": project_id}


def list_runs(user_id: int, project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, project_id, name, description, finished_at, elapsed_sec,
                   COALESCE(result->'metrics', '{}'::jsonb) AS metrics,
                   NULLIF(TRIM(COALESCE(
                     request->>'universe',
                     result->'meta'->>'universe',
                     ''
                   )), '') AS universe
            FROM strategy_runs
            WHERE user_id = %s AND project_id = %s
            ORDER BY finished_at DESC
            """,
            (user_id, project_id),
        ).fetchall()
    runs = []
    for r in rows:
        row = dict(r)
        metrics = row.get("metrics") or {}
        if isinstance(metrics, str):
            metrics = json.loads(metrics)
        universe = row.get("universe") or ""
        # 列表不返回完整 request（含 strategy_code），只带历史表需要的摘要字段
        slim_req: dict[str, Any] = {}
        if universe:
            slim_req["universe"] = universe
        runs.append(
            {
                "id": row["id"],
                "projectId": row["project_id"],
                "name": row.get("name") or "",
                "description": row.get("description") or "",
                "request": slim_req,
                "result": {"metrics": metrics},
                "finishedAt": _iso(row.get("finished_at")),
                "elapsedSec": float(row.get("elapsed_sec") or 0),
            }
        )
    return {"ok": True, "user_id": int(user_id), "runs": runs}


def get_run(user_id: int, run_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_runs WHERE user_id = %s AND id = %s",
            (user_id, run_id),
        ).fetchone()
    if not row:
        raise KeyError(run_id)
    return {"ok": True, "run": _row_run(dict(row))}


def save_run(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("projectId") or payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("缺少 projectId")
    run_id = str(payload.get("id") or "").strip() or str(uuid.uuid4())
    name = str(payload.get("name") or "").strip()
    description = str(payload.get("description") or name).strip()
    request = payload.get("request") or {}
    result = payload.get("result") or {}
    finished_at = payload.get("finishedAt") or payload.get("finished_at")
    elapsed = float(payload.get("elapsedSec") or payload.get("elapsed_sec") or 0)

    with get_conn() as conn:
        proj = conn.execute(
            "SELECT id, name FROM strategy_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        ).fetchone()
        if not proj:
            raise KeyError(f"project:{project_id}")
        if not name:
            name = proj["name"] or "策略回测"
        row = conn.execute(
            """
            INSERT INTO strategy_runs
              (id, user_id, project_id, name, description, request, result, finished_at, elapsed_sec)
            VALUES (
              %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
              COALESCE(%s::timestamptz, NOW()), %s
            )
            ON CONFLICT (user_id, id) DO UPDATE SET
              request = EXCLUDED.request,
              result = EXCLUDED.result,
              finished_at = EXCLUDED.finished_at,
              elapsed_sec = EXCLUDED.elapsed_sec
            RETURNING *
            """,
            (
                run_id,
                user_id,
                project_id,
                name,
                description,
                json.dumps(request, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                finished_at,
                elapsed,
            ),
        ).fetchone()
        conn.execute(
            """
            UPDATE strategy_projects
            SET run_count = (
                  SELECT COUNT(*) FROM strategy_runs
                  WHERE user_id = %s AND project_id = %s
                ),
                updated_at = NOW()
            WHERE user_id = %s AND id = %s
            """,
            (user_id, project_id, user_id, project_id),
        )
        proj_row = conn.execute(
            "SELECT * FROM strategy_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        ).fetchone()
    return {
        "ok": True,
        "user_id": int(user_id),
        "run": _row_run(dict(row)),
        "project": _row_project(dict(proj_row)) if proj_row else None,
    }


def delete_run(user_id: int, run_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "DELETE FROM strategy_runs WHERE user_id = %s AND id = %s RETURNING project_id",
            (user_id, run_id),
        ).fetchone()
        if not row:
            raise KeyError(run_id)
        project_id = row["project_id"]
        conn.execute(
            """
            UPDATE strategy_projects
            SET run_count = (
                  SELECT COUNT(*) FROM strategy_runs
                  WHERE user_id = %s AND project_id = %s
                ),
                updated_at = NOW()
            WHERE user_id = %s AND id = %s
            """,
            (user_id, project_id, user_id, project_id),
        )
    return {"ok": True, "id": run_id}
