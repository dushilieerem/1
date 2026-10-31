# -*- coding: utf-8 -*-
"""因子检测项目 / 记录：按 user_id 隔离，存 Postgres。"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from typing import Any

from services.core.db import get_conn

SAMPLE_ID = "sample_momentum_5d"

_schema_lock = threading.Lock()
# 升版本号以在进程重启后跑新的 ADD COLUMN（如 flagged）
_schema_ready = False
_SCHEMA_VERSION = 2
_schema_applied_version = 0


def ensure_detect_schema() -> None:
    """建表/补列只跑一次。并发请求同时 ALTER 会抢 AccessExclusiveLock 死锁。"""
    global _schema_ready, _schema_applied_version
    if _schema_ready and _schema_applied_version >= _SCHEMA_VERSION:
        return
    with _schema_lock:
        if _schema_ready and _schema_applied_version >= _SCHEMA_VERSION:
            return
        with get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS detect_projects (
                  id            TEXT NOT NULL,
                  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  name          TEXT NOT NULL,
                  factor_name   TEXT NOT NULL,
                  description   TEXT NOT NULL DEFAULT '',
                  config        JSONB NOT NULL DEFAULT '{}'::jsonb,
                  run_count     INTEGER NOT NULL DEFAULT 0,
                  is_sample     BOOLEAN NOT NULL DEFAULT FALSE,
                  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (user_id, id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_detect_projects_user_updated "
                "ON detect_projects (user_id, updated_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS detect_runs (
                  id            TEXT NOT NULL,
                  user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  project_id    TEXT NOT NULL,
                  factor_name   TEXT NOT NULL,
                  description   TEXT NOT NULL DEFAULT '',
                  request       JSONB NOT NULL DEFAULT '{}'::jsonb,
                  result        JSONB NOT NULL DEFAULT '{}'::jsonb,
                  finished_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  elapsed_sec   DOUBLE PRECISION NOT NULL DEFAULT 0,
                  PRIMARY KEY (user_id, id),
                  CONSTRAINT detect_runs_project_fk
                    FOREIGN KEY (user_id, project_id)
                    REFERENCES detect_projects (user_id, id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_detect_runs_project "
                "ON detect_runs (user_id, project_id, finished_at DESC)"
            )
            conn.execute(
                """
                ALTER TABLE detect_runs
                  ADD COLUMN IF NOT EXISTS remark TEXT NOT NULL DEFAULT ''
                """
            )
            conn.execute(
                """
                ALTER TABLE detect_runs
                  ADD COLUMN IF NOT EXISTS flagged BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_detect_runs_user_finished "
                "ON detect_runs (user_id, finished_at DESC)"
            )
        _schema_ready = True
        _schema_applied_version = _SCHEMA_VERSION


def _iso(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.isoformat()
    return val


def _default_config(factor_codes: list[str] | None = None) -> dict[str, Any]:
    codes = list(factor_codes or [])
    n = len(codes)
    return {
        "factorCodes": codes,
        "weightMode": "sum",
        "weights": ([round(100 / n, 4)] * n) if n else [],
        "powers": [1] * n if n else [],
        "customCombine": (
            f'def combo_factor(self):\n    """自定义组合"""\n    return self.{codes[0]}()'
            if codes
            else 'def combo_factor(self):\n    """自定义组合"""\n    return self.close.pct_change(5)'
        ),
        "portfolioType": "long_only",
        "rangeMode": "period",
        "backtestPeriod": "3y",
        "startDate": "",
        "endDate": "",
        "universe": "CSI300",
        "benchmark": "CSI300",
        "groups": 5,
        "rebalanceDays": 1,
        "filterLimitUp": False,
        "filterSuspended": False,
        "analysisLevel": "core",
        "commissionRate": 0,
        "stampTax": 0,
        "slippageRate": 0,
    }


def _row_project(row: dict[str, Any]) -> dict[str, Any]:
    cfg = row.get("config") or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    return {
        "id": row["id"],
        "name": row["name"],
        "factorName": row["factor_name"],
        "description": row.get("description") or "",
        "createdAt": _iso(row.get("created_at")),
        "updatedAt": _iso(row.get("updated_at")),
        "runCount": int(row.get("run_count") or 0),
        "sample": bool(row.get("is_sample")),
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
        "factorName": row["factor_name"],
        "description": row.get("description") or "",
        "remark": row.get("remark") or "",
        "flagged": bool(row.get("flagged")),
        "request": req,
        "result": res,
        "verified": bool((res or {}).get("_svquant_verified")),
        "finishedAt": _iso(row.get("finished_at")),
        "elapsedSec": float(row.get("elapsed_sec") or 0),
    }


def ensure_sample_project(user_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM detect_projects WHERE user_id = %s AND id = %s",
            (user_id, SAMPLE_ID),
        ).fetchone()
        if row:
            return _row_project(dict(row))
        cfg = _default_config(["momentum_5d"])
        row = conn.execute(
            """
            INSERT INTO detect_projects
              (id, user_id, name, factor_name, description, config, run_count, is_sample)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, 0, TRUE)
            RETURNING *
            """,
            (
                SAMPLE_ID,
                user_id,
                "5日动量",
                "momentum_5d",
                "5日动量",
                json.dumps(cfg, ensure_ascii=False),
            ),
        ).fetchone()
        return _row_project(dict(row))


def list_projects(user_id: int, *, visible_only: bool = False) -> dict[str, Any]:
    ensure_sample_project(user_id)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM detect_projects
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
        projects = [p for p in projects if p.get("sample") or (p.get("runCount") or 0) > 0]
    return {
        "ok": True,
        "user_id": int(user_id),
        "username": (uname["username"] if uname else None),
        "projects": projects,
    }


def transfer_project_to_user(project_id: str, from_user_id: int, to_user_id: int) -> bool:
    """把错归属的检测项目（含 runs）迁到正确用户。同 id 已存在则跳过。"""
    if from_user_id == to_user_id:
        return False
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM detect_projects WHERE user_id = %s AND id = %s",
            (to_user_id, project_id),
        ).fetchone()
        if exists:
            return False
        src = conn.execute(
            "SELECT * FROM detect_projects WHERE user_id = %s AND id = %s",
            (from_user_id, project_id),
        ).fetchone()
        if not src:
            return False
        cfg = src["config"]
        if not isinstance(cfg, str):
            cfg = json.dumps(cfg, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO detect_projects
              (id, user_id, name, factor_name, description, config, run_count, is_sample, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                src["id"],
                to_user_id,
                src["name"],
                src["factor_name"],
                src["description"],
                cfg,
                src["run_count"],
                src["is_sample"],
                src["created_at"],
                src["updated_at"],
            ),
        )
        runs = conn.execute(
            "SELECT * FROM detect_runs WHERE user_id = %s AND project_id = %s",
            (from_user_id, project_id),
        ).fetchall()
        for r in runs:
            req = r["request"]
            res = r["result"]
            if not isinstance(req, str):
                req = json.dumps(req, ensure_ascii=False)
            if not isinstance(res, str):
                res = json.dumps(res, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO detect_runs
                  (id, user_id, project_id, factor_name, description, request, result, finished_at, elapsed_sec)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                """,
                (
                    r["id"],
                    to_user_id,
                    project_id,
                    r["factor_name"],
                    r["description"],
                    req,
                    res,
                    r["finished_at"],
                    r["elapsed_sec"],
                ),
            )
        conn.execute(
            "DELETE FROM detect_projects WHERE user_id = %s AND id = %s",
            (from_user_id, project_id),
        )
    return True


def reassign_misowned_named_projects() -> list[str]:
    """把 name 恰好等于某用户名、却挂在别人名下的项目迁回该用户。"""
    notes: list[str] = []
    with get_conn() as conn:
        users = {
            r["username"]: int(r["id"])
            for r in conn.execute("SELECT id, username FROM users").fetchall()
        }
        rows = conn.execute(
            """
            SELECT id, user_id, name FROM detect_projects
            WHERE is_sample = FALSE AND name = ANY(%s)
            """,
            (list(users.keys()),),
        ).fetchall()
    for row in rows:
        target = users.get(row["name"])
        if not target or int(row["user_id"]) == target:
            continue
        ok = transfer_project_to_user(row["id"], int(row["user_id"]), target)
        if ok:
            notes.append(f"{row['name']}: {row['user_id']} -> {target} ({row['id']})")
    return notes


def get_project(user_id: int, project_id: str) -> dict[str, Any]:
    ensure_sample_project(user_id)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM detect_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        ).fetchone()
    if not row:
        raise KeyError(project_id)
    return {"ok": True, "user_id": int(user_id), "project": _row_project(dict(row))}


def upsert_project(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    pid = str(payload.get("id") or "").strip() or str(uuid.uuid4())
    name = str(payload.get("name") or payload.get("description") or "未命名").strip()
    factor_name = str(payload.get("factorName") or payload.get("factor_name") or "custom_combo").strip()
    description = str(payload.get("description") or name).strip()
    config = payload.get("config") or _default_config(
        [factor_name] if factor_name not in ("", "custom_combo") else []
    )
    is_sample = bool(payload.get("sample") or payload.get("is_sample"))
    if pid == SAMPLE_ID:
        is_sample = True

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT run_count, is_sample FROM detect_projects WHERE user_id = %s AND id = %s",
            (user_id, pid),
        ).fetchone()
        if existing:
            row = conn.execute(
                """
                UPDATE detect_projects
                SET name = %s, factor_name = %s, description = %s,
                    config = %s::jsonb, updated_at = NOW()
                WHERE user_id = %s AND id = %s
                RETURNING *
                """,
                (
                    name,
                    factor_name,
                    description,
                    json.dumps(config, ensure_ascii=False),
                    user_id,
                    pid,
                ),
            ).fetchone()
        else:
            row = conn.execute(
                """
                INSERT INTO detect_projects
                  (id, user_id, name, factor_name, description, config, run_count, is_sample)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, 0, %s)
                RETURNING *
                """,
                (
                    pid,
                    user_id,
                    name,
                    factor_name,
                    description,
                    json.dumps(config, ensure_ascii=False),
                    is_sample,
                ),
            ).fetchone()
    return {"ok": True, "user_id": int(user_id), "project": _row_project(dict(row))}


def create_project(
    user_id: int,
    *,
    factor_name: str,
    description: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    title = (display_name or description or factor_name).strip()
    codes = [factor_name] if factor_name and factor_name != "custom_combo" else []
    return upsert_project(
        user_id,
        {
            "id": str(uuid.uuid4()),
            "name": title,
            "factorName": factor_name,
            "description": description or title,
            "config": _default_config(codes),
            "sample": False,
        },
    )


def delete_project(user_id: int, project_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT is_sample FROM detect_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        ).fetchone()
        if not row:
            raise KeyError(project_id)
        if row["is_sample"]:
            return {"ok": True, "skipped": "sample"}
        conn.execute(
            "DELETE FROM detect_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        )
    return {"ok": True, "id": project_id}


def list_runs(user_id: int, project_id: str) -> dict[str, Any]:
    """历史列表：只返回表格摘要（含 UI 因子快照），不碰 result 大 JSON。"""
    return _list_runs_query(user_id, project_id=project_id)


def list_all_runs(user_id: int) -> dict[str, Any]:
    """当前用户全部检测运行（全局检测报告列表）。"""
    return _list_runs_query(user_id, project_id=None)


def _list_runs_query(user_id: int, *, project_id: str | None) -> dict[str, Any]:
    """列表摘要：故意不碰 result JSONB。

    单条 result 常约 100KB–1MB（净值曲线等）。Postgres 取 result->'metrics'
    仍会把整段 TOAST 解出来；用户几百条时列表可卡 1–2s+。详情走 get_run。
    """
    ensure_detect_schema()
    with get_conn() as conn:
        if project_id:
            rows = conn.execute(
                """
                SELECT id, project_id, factor_name, description, remark, flagged,
                       finished_at, elapsed_sec,
                       request->'_svquant_ui' AS ui_snap,
                       request->>'factor_name' AS req_factor_name
                FROM detect_runs
                WHERE user_id = %s AND project_id = %s
                ORDER BY finished_at DESC
                """,
                (user_id, project_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, project_id, factor_name, description, remark, flagged,
                       finished_at, elapsed_sec,
                       request->'_svquant_ui' AS ui_snap,
                       request->>'factor_name' AS req_factor_name
                FROM detect_runs
                WHERE user_id = %s
                ORDER BY finished_at DESC
                """,
                (user_id,),
            ).fetchall()
    runs = []
    for r in rows:
        row = dict(r)
        ui = row.get("ui_snap") or {}
        if isinstance(ui, str):
            try:
                ui = json.loads(ui)
            except Exception:
                ui = {}
        if not isinstance(ui, dict):
            ui = {}
        codes = ui.get("factorCodes") or []
        labels = ui.get("factorLabels") or {}
        if not isinstance(labels, dict):
            labels = {}
        summary = ""
        if isinstance(codes, list) and codes:
            parts = [str(labels.get(c) or c) for c in codes]
            if len(parts) <= 3:
                summary = " + ".join(parts)
            else:
                summary = f"{parts[0]} + {parts[1]} 等{len(parts)}个"
        desc = summary or (row.get("description") or "") or (row.get("req_factor_name") or "")
        slim_req: dict[str, Any] = {}
        if ui:
            slim_req["_svquant_ui"] = {
                "factorCodes": codes if isinstance(codes, list) else [],
                "factorLabels": labels,
            }
        if row.get("req_factor_name"):
            slim_req["factor_name"] = row["req_factor_name"]
        runs.append(
            {
                "id": row["id"],
                "projectId": row["project_id"],
                "factorName": row["factor_name"],
                "description": desc,
                "remark": row.get("remark") or "",
                "flagged": bool(row.get("flagged")),
                "request": slim_req,
                # 列表不带绩效；打开报告页再 get_run 拉完整 result
                "result": {},
                "finishedAt": _iso(row.get("finished_at")),
                "elapsedSec": float(row.get("elapsed_sec") or 0),
            }
        )
    return {"ok": True, "user_id": int(user_id), "runs": runs}


def get_run(user_id: int, run_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM detect_runs WHERE user_id = %s AND id = %s",
            (user_id, run_id),
        ).fetchone()
    if not row:
        raise KeyError(run_id)
    return {"ok": True, "run": _row_run(dict(row))}


def _verified_detect_result(user_id: int, result: Any) -> Any:
    """P1-F09：校验 BFF 签名。

    - 带签名且错误：拒绝入库（客户端伪造/篡改结果）
    - 带签名且正确：标记 `_svquant_verified=true`
    - 无签名（旧客户端/历史数据）：按未验证保存
    """
    if not isinstance(result, dict):
        return result
    result = dict(result)
    token = str(result.pop("_svquant_verified_token", "") or "")
    verified = False
    if token:
        from services.strategy.result_signature import verify_result

        if not verify_result(user_id, result, token):
            raise ValueError("检测结果签名无效，已拒绝入库")
        verified = True
    return {**result, "_svquant_verified": verified}


def save_run(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_detect_schema()
    project_id = str(payload.get("projectId") or payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("缺少 projectId")
    run_id = str(payload.get("id") or "").strip() or str(uuid.uuid4())
    factor_name = str(payload.get("factorName") or payload.get("factor_name") or "").strip()
    description = str(payload.get("description") or factor_name).strip()
    remark = str(payload.get("remark") or "").strip()
    request = payload.get("request") or {}
    result = payload.get("result") or {}
    result = _verified_detect_result(user_id, result)
    finished_at = payload.get("finishedAt") or payload.get("finished_at")
    elapsed = float(payload.get("elapsedSec") or payload.get("elapsed_sec") or 0)

    with get_conn() as conn:
        proj = conn.execute(
            "SELECT id FROM detect_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        ).fetchone()
        if not proj:
            raise KeyError(f"project:{project_id}")
        row = conn.execute(
            """
            INSERT INTO detect_runs
              (id, user_id, project_id, factor_name, description, remark,
               request, result, finished_at, elapsed_sec)
            VALUES (
              %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
              COALESCE(%s::timestamptz, NOW()), %s
            )
            ON CONFLICT (user_id, id) DO UPDATE SET
              request = EXCLUDED.request,
              result = EXCLUDED.result,
              finished_at = EXCLUDED.finished_at,
              elapsed_sec = EXCLUDED.elapsed_sec,
              remark = COALESCE(NULLIF(EXCLUDED.remark, ''), detect_runs.remark)
            RETURNING *
            """,
            (
                run_id,
                user_id,
                project_id,
                factor_name,
                description,
                remark,
                json.dumps(request, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                finished_at,
                elapsed,
            ),
        ).fetchone()
        conn.execute(
            """
            UPDATE detect_projects
            SET run_count = (
                  SELECT COUNT(*) FROM detect_runs
                  WHERE user_id = %s AND project_id = %s
                ),
                updated_at = NOW()
            WHERE user_id = %s AND id = %s
            """,
            (user_id, project_id, user_id, project_id),
        )
        proj_row = conn.execute(
            "SELECT * FROM detect_projects WHERE user_id = %s AND id = %s",
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
            "DELETE FROM detect_runs WHERE user_id = %s AND id = %s RETURNING project_id",
            (user_id, run_id),
        ).fetchone()
        if not row:
            raise KeyError(run_id)
        project_id = row["project_id"]
        conn.execute(
            """
            UPDATE detect_projects
            SET run_count = (
                  SELECT COUNT(*) FROM detect_runs
                  WHERE user_id = %s AND project_id = %s
                ),
                updated_at = NOW()
            WHERE user_id = %s AND id = %s
            """,
            (user_id, project_id, user_id, project_id),
        )
    return {"ok": True, "id": run_id}


def update_run_remark(user_id: int, run_id: int | str, remark: str) -> dict[str, Any]:
    ensure_detect_schema()
    rid = str(run_id).strip()
    text = (remark or "").strip()
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE detect_runs
            SET remark = %s
            WHERE user_id = %s AND id = %s
            RETURNING *
            """,
            (text, user_id, rid),
        ).fetchone()
    if not row:
        raise KeyError(rid)
    return {"ok": True, "run": _row_run(dict(row))}


def update_run_flagged(user_id: int, run_id: int | str, flagged: bool) -> dict[str, Any]:
    ensure_detect_schema()
    rid = str(run_id).strip()
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE detect_runs
            SET flagged = %s
            WHERE user_id = %s AND id = %s
            RETURNING *
            """,
            (bool(flagged), user_id, rid),
        ).fetchone()
    if not row:
        raise KeyError(rid)
    return {"ok": True, "run": _row_run(dict(row))}
