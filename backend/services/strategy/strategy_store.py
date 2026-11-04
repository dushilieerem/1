# -*- coding: utf-8 -*-
"""策略研究项目 / 回测记录：按 user_id 隔离，存 Postgres。

完整回测结果（含全部调仓日志）另存 gzip 文件；库内仅摘要，避免大 JSONB OOM。
"""
from __future__ import annotations

import gzip
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from services.core.db import get_conn
from services.strategy.result_signature import result_hash, verify_result

SAMPLE_ID = "sample_momentum_20d"
SAMPLE_NAME = "多因子合成 样例"

# 新建策略默认：空因子，用户自选
DEFAULT_STRATEGY_CODE = '''from app.services.strategy.vectorized.factor_strategy import (
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
RANGE_MODE = "period"
BACKTEST_PERIOD = "10y"
START_DATE = ""
END_DATE = ""
COMMISSION_RATE = 0.0003
STAMP_TAX = 0.001
SLIPPAGE_RATE = 0.001
INITIAL_CAPITAL = 1_000_000
TOP_N = 30
REBALANCE_DAYS = 20
# --- SVQUANT_PARAMS_END ---


class MyStrategy(FactorPortfolioStrategy):
    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    # --- SVQUANT_FACTORS_BEGIN ---
    # 请从左侧选择因子（可不选，也可在右侧手写 @factor）
    # --- SVQUANT_FACTORS_END ---

    # --- SVQUANT_EXTRA_BEGIN （信号外逻辑，可手写） ---
    def _post_signal(self, raw):
        """信号外逻辑钩子：默认透传。可在此做趋势门控 / 过滤。"""
        return raw
    # --- SVQUANT_EXTRA_END ---

    # --- SVQUANT_SIGNAL_BEGIN ---
    @signal
    def score(self):
        raw = self.close.pct_change(20) * 0  # 请选择因子
        return self._post_signal(raw)
    # --- SVQUANT_SIGNAL_END ---
'''

# 样例：多因子赋权相加，演示 @signal 合成写法
SAMPLE_STRATEGY_CODE = '''from app.services.strategy.vectorized.factor_strategy import (
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
RANGE_MODE = "period"
BACKTEST_PERIOD = "10y"
START_DATE = ""
END_DATE = ""
COMMISSION_RATE = 0.0003
STAMP_TAX = 0.001
SLIPPAGE_RATE = 0.001
INITIAL_CAPITAL = 1_000_000
TOP_N = 30
REBALANCE_DAYS = 20
# --- SVQUANT_PARAMS_END ---


class MultiFactorSampleStrategy(FactorPortfolioStrategy):
    """样例：动量 + 小市值 + 价值，赋权相加合成。"""

    selector = TopN(30)
    weighting = EqualWeight()
    rebalance = EveryNTradingDays(20)

    # --- SVQUANT_FACTORS_BEGIN ---
    @factor
    def momentum_20d(self):
        """20 日动量（约月）。"""
        return self.close.pct_change(20)

    @factor
    def small_size(self):
        """小市值：负总市值。"""
        return -self.current_mv

    @factor
    def ep_ttm(self):
        """EP 因子：滚动市盈率倒数。"""
        return 1.0 / self.pe_ttm
    # --- SVQUANT_FACTORS_END ---

    # --- SVQUANT_EXTRA_BEGIN （信号外逻辑，可手写） ---
    def _post_signal(self, raw):
        """信号外逻辑钩子：默认透传。可在此做趋势门控 / 过滤。"""
        return raw
    # --- SVQUANT_EXTRA_END ---

    # --- SVQUANT_SIGNAL_BEGIN ---
    @signal
    def score(self):
        # 赋权相加：截面 rank 后加权（权重 50% / 30% / 20%）
        raw = (
            0.5 * self.rank(self.momentum_20d()) +
            0.3 * self.rank(self.small_size()) +
            0.2 * self.rank(self.ep_ttm())
        )
        return self._post_signal(raw)
    # --- SVQUANT_SIGNAL_END ---
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
              is_sample     BOOLEAN NOT NULL DEFAULT FALSE,
              created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (user_id, id)
            )
            """
        )
        # 旧库补列
        conn.execute(
            "ALTER TABLE strategy_projects "
            "ADD COLUMN IF NOT EXISTS is_sample BOOLEAN NOT NULL DEFAULT FALSE"
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
              verified      BOOLEAN NOT NULL DEFAULT FALSE,
              result_hash   TEXT,
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
        conn.execute(
            "ALTER TABLE strategy_runs "
            "ADD COLUMN IF NOT EXISTS remark TEXT NOT NULL DEFAULT ''"
        )
        conn.execute(
            "ALTER TABLE strategy_runs "
            "ADD COLUMN IF NOT EXISTS flagged BOOLEAN NOT NULL DEFAULT FALSE"
        )
        conn.execute(
            "ALTER TABLE strategy_runs "
            "ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE"
        )
        conn.execute(
            "ALTER TABLE strategy_runs "
            "ADD COLUMN IF NOT EXISTS result_hash TEXT"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_strategy_runs_user_finished "
            "ON strategy_runs (user_id, finished_at DESC)"
        )


def _iso(val: Any) -> Any:
    if isinstance(val, datetime):
        return val.isoformat()
    return val


def _default_config() -> dict[str, Any]:
    """新建策略：空因子 + 调仓日志默认开。"""
    return {
        "universe": "CSI500",
        "benchmark": "CSI300",
        "rangeMode": "period",
        "backtestPeriod": "3y",
        "startDate": "",
        "endDate": "",
        "commission_rate": 0.0003,
        "stamp_tax": 0.001,
        "slippage_rate": 0.001,
        "initial_capital": 1_000_000,
        "top_n": 30,
        "rebalance_days": 20,
        "include_rebalance_logs": True,
        "strategy_code": DEFAULT_STRATEGY_CODE,
        "signal_factor_ids": [],
        "signal_factor_weights": [],
        "signal_factor_powers": [],
        "signal_weight_mode": "sum",
    }


def _sample_config() -> dict[str, Any]:
    """系统样例：多因子赋权相加。"""
    return {
        **_default_config(),
        "strategy_code": SAMPLE_STRATEGY_CODE,
        "signal_factor_ids": ["momentum_20d", "small_size", "ep_ttm"],
        "signal_factor_weights": [50, 30, 20],
        "signal_factor_powers": [1, 1, 1],
        "signal_weight_mode": "sum",
        "include_rebalance_logs": True,
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
        "name": row.get("name") or "",
        "description": row.get("description") or "",
        "remark": row.get("remark") or "",
        "flagged": bool(row.get("flagged")),
        "verified": bool(row.get("verified")),
        "resultHash": row.get("result_hash"),
        "request": req,
        "result": res,
        "finishedAt": _iso(row.get("finished_at")),
        "elapsedSec": float(row.get("elapsed_sec") or 0),
    }


# 完整回测结果（含全部调仓日志）走磁盘 gzip；Postgres 只存摘要，避免 PortalContext OOM。
_BLOB_ROOT = Path(__file__).resolve().parents[2] / "data" / "strategy_run_blobs"


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _blob_path(user_id: int, run_id: str) -> Path:
    """run_id 只允许服务端 UUID/安全字符；拒绝路径穿越。"""
    rid = str(run_id or "")
    if not _RUN_ID_RE.fullmatch(rid):
        raise ValueError("run_id 非法")
    root = (_BLOB_ROOT / str(int(user_id))).resolve()
    path = (root / f"{rid}.json.gz").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("run_id 非法") from exc
    return path


def _json_default(obj: Any) -> Any:
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):  # NaN / Inf
            return None
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, default=_json_default)


def _strip_code_hash(value: Any) -> Any:
    """策略运行记录不持久化 code_hash，兼容嵌套结果 JSON。"""
    if isinstance(value, dict):
        return {
            str(key): _strip_code_hash(item)
            for key, item in value.items()
            if str(key) != "code_hash"
        }
    if isinstance(value, list):
        return [_strip_code_hash(item) for item in value]
    return value


def write_run_blob(user_id: int, run_id: str, payload: dict[str, Any]) -> Path:
    path = _blob_path(user_id, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _dumps(payload).encode("utf-8")
    with gzip.open(path, "wb", compresslevel=6) as f:
        f.write(raw)
    return path


def read_run_blob(user_id: int, run_id: str) -> dict[str, Any] | None:
    path = _blob_path(user_id, run_id)
    if not path.is_file():
        return None
    with gzip.open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def delete_run_blob(user_id: int, run_id: str) -> None:
    path = _blob_path(user_id, run_id)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def slim_strategy_result_for_db(result: Any) -> dict[str, Any]:
    """Postgres 摘要：指标 + 曲线；不含完整调仓日志。"""
    if not isinstance(result, dict):
        return {}
    out: dict[str, Any] = {
        "metrics": result.get("metrics"),
        "date_range": result.get("date_range"),
        "final_equity": result.get("final_equity"),
        "excess_return": result.get("excess_return"),
        "meta": result.get("meta"),
        "drawdowns": result.get("drawdowns"),
        "annual_returns": result.get("annual_returns"),
        "equity_curve": result.get("equity_curve"),
        "benchmark_curve": result.get("benchmark_curve"),
        "error": result.get("error"),
        "_full_result_blob": True,
    }
    logs = result.get("rebalance_logs")
    if isinstance(logs, list):
        out["_rebalance_logs_count"] = len(logs)
    return out


def slim_strategy_request(request: Any) -> dict[str, Any]:
    """保留完整 request 快照；特别是 strategy_code 不截断。"""
    if not isinstance(request, dict):
        return {}
    return dict(request)


def _attach_builtin_source_snapshot(request: Any) -> dict[str, Any]:
    """为 ID-only 内置回测补齐 request JSONB 中的源码快照。

    RE 执行只收到 strategy_id；这里的源码来自 SVQuant 中保留的过渡期
    快照，只用于历史记录，不改变实际执行请求，也不计算/保存 code_hash。
    """
    if not isinstance(request, dict):
        return {}
    out = dict(request)
    strategy_id = str(out.get("strategy_id") or "").strip()
    if not strategy_id or str(out.get("strategy_code") or "").strip():
        return out
    try:
        from services.strategy.builtin_strategies_store import get_builtin_strategy

        source = str(get_builtin_strategy(strategy_id).get("strategy_code") or "")
    except (KeyError, ValueError):
        source = ""
    if source:
        out["strategy_code"] = source
    return out


def ensure_sample_project(user_id: int) -> dict[str, Any]:
    """每用户一条多因子合成样例（演示赋权相加 @signal）。"""
    ensure_strategy_schema()
    cfg = _sample_config()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_projects WHERE user_id = %s AND id = %s",
            (user_id, SAMPLE_ID),
        ).fetchone()
        if row:
            cfg_raw = row.get("config") or {}
            if isinstance(cfg_raw, str):
                cfg_raw = json.loads(cfg_raw)
            ids = cfg_raw.get("signal_factor_ids") or []
            name = str(row["name"] or "")
            # 旧单因子样例 → 升为多因子
            if name == "20日动量 样例" or len(ids) < 2:
                row = conn.execute(
                    """
                    UPDATE strategy_projects
                    SET name = %s, description = %s, config = %s::jsonb, updated_at = NOW()
                    WHERE user_id = %s AND id = %s
                    RETURNING *
                    """,
                    (
                        SAMPLE_NAME,
                        "多因子合成样例 · 赋权相加（动量/小市值/价值）",
                        json.dumps(cfg, ensure_ascii=False),
                        user_id,
                        SAMPLE_ID,
                    ),
                ).fetchone()
            return _row_project(dict(row))
        row = conn.execute(
            """
            INSERT INTO strategy_projects
              (id, user_id, name, description, config, run_count, is_sample)
            VALUES (%s, %s, %s, %s, %s::jsonb, 0, TRUE)
            RETURNING *
            """,
            (
                SAMPLE_ID,
                user_id,
                SAMPLE_NAME,
                "多因子合成样例 · 赋权相加（动量/小市值/价值）",
                json.dumps(cfg, ensure_ascii=False),
            ),
        ).fetchone()
        return _row_project(dict(row))


def list_projects(user_id: int, *, visible_only: bool = False) -> dict[str, Any]:
    ensure_sample_project(user_id)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM strategy_projects
            WHERE user_id = %s
            ORDER BY is_sample ASC, updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        uname = conn.execute(
            "SELECT username FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    projects = [_row_project(dict(r)) for r in rows]
    if visible_only:
        projects = [
            p for p in projects if p.get("sample") or (p.get("runCount") or 0) > 0
        ]
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
    # 内置策略过渡期只保存 strategy_id，源码不需要进入研究编辑器。
    # 普通/用户策略仍沿用默认源码模板。
    if (
        not str(config.get("strategy_code") or "").strip()
        and not str(config.get("strategy_id") or "").strip()
    ):
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
            "SELECT is_sample FROM strategy_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        ).fetchone()
        if not row:
            raise KeyError(project_id)
        if row["is_sample"]:
            return {"ok": True, "skipped": "sample"}
        run_ids = conn.execute(
            "SELECT id FROM strategy_runs WHERE user_id = %s AND project_id = %s",
            (user_id, project_id),
        ).fetchall()
        conn.execute(
            "DELETE FROM strategy_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        )
    for r in run_ids:
        delete_run_blob(user_id, str(r["id"]))
    return {"ok": True, "id": project_id}


def list_runs(user_id: int, project_id: str) -> dict[str, Any]:
    return _list_runs_query(user_id, project_id=project_id)


def list_all_runs(user_id: int) -> dict[str, Any]:
    """当前用户全部策略回测报告（对标 detect list_all_runs）。"""
    return _list_runs_query(user_id, project_id=None)


def _list_runs_query(user_id: int, *, project_id: str | None) -> dict[str, Any]:
    with get_conn() as conn:
        if project_id:
            rows = conn.execute(
                """
                SELECT id, project_id, name, description, remark, flagged, verified, result_hash,
                       finished_at, elapsed_sec,
                       COALESCE(result->'metrics', '{}'::jsonb) AS metrics,
                       COALESCE(result->'date_range', '{}'::jsonb) AS date_range,
                       COALESCE(request->'quant_factors', '[]'::jsonb) AS quant_factors,
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
        else:
            rows = conn.execute(
                """
                SELECT id, project_id, name, description, remark, flagged, verified, result_hash,
                       finished_at, elapsed_sec,
                       COALESCE(result->'metrics', '{}'::jsonb) AS metrics,
                       COALESCE(result->'date_range', '{}'::jsonb) AS date_range,
                       COALESCE(request->'quant_factors', '[]'::jsonb) AS quant_factors,
                       NULLIF(TRIM(COALESCE(
                         request->>'universe',
                         result->'meta'->>'universe',
                         ''
                       )), '') AS universe
                FROM strategy_runs
                WHERE user_id = %s
                ORDER BY finished_at DESC
                """,
                (user_id,),
            ).fetchall()
    runs = []
    for r in rows:
        row = dict(r)
        metrics = row.get("metrics") or {}
        if isinstance(metrics, str):
            metrics = json.loads(metrics)
        universe = row.get("universe") or ""
        slim_req: dict[str, Any] = {}
        if universe:
            slim_req["universe"] = universe
        quant_factors = row.get("quant_factors")
        if isinstance(quant_factors, str):
            try:
                quant_factors = json.loads(quant_factors)
            except ValueError:
                quant_factors = []
        if quant_factors:
            slim_req["quant_factors"] = quant_factors
        date_range = row.get("date_range") or {}
        if isinstance(date_range, str):
            try:
                date_range = json.loads(date_range)
            except ValueError:
                date_range = {}
        runs.append(
            {
                "id": row["id"],
                "projectId": row["project_id"],
                "name": row.get("name") or "",
                "description": row.get("description") or "",
                "remark": row.get("remark") or "",
                "flagged": bool(row.get("flagged")),
                "verified": bool(row.get("verified")),
                "request": slim_req,
                "result": {"metrics": metrics, "date_range": date_range},
                "finishedAt": _iso(row.get("finished_at")),
                "elapsedSec": float(row.get("elapsed_sec") or 0),
            }
        )
    return {"ok": True, "user_id": int(user_id), "runs": runs}


def update_run_remark(user_id: int, run_id: str, remark: str) -> dict[str, Any]:
    text = (remark or "").strip()
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE strategy_runs
            SET remark = %s
            WHERE user_id = %s AND id = %s
            RETURNING *
            """,
            (text, user_id, run_id),
        ).fetchone()
    if not row:
        raise KeyError(run_id)
    return {"ok": True, "run": _row_run(dict(row))}


def update_run_flagged(user_id: int, run_id: str, flagged: bool) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE strategy_runs
            SET flagged = %s
            WHERE user_id = %s AND id = %s
            RETURNING *
            """,
            (bool(flagged), user_id, run_id),
        ).fetchone()
    if not row:
        raise KeyError(run_id)
    return {"ok": True, "run": _row_run(dict(row))}


def get_run(user_id: int, run_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_runs WHERE user_id = %s AND id = %s",
            (user_id, run_id),
        ).fetchone()
    if not row:
        raise KeyError(run_id)
    run = _row_run(dict(row))
    blob = read_run_blob(user_id, run_id)
    if blob and isinstance(blob.get("result"), dict):
        run["result"] = blob["result"]
        if isinstance(blob.get("request"), dict) and blob["request"]:
            # 文件里保存的是完整 request 快照
            run["request"] = {**run["request"], **blob["request"]}
    return {"ok": True, "run": run}


def save_run(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("projectId") or payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("缺少 projectId")
    run_id = str(payload.get("id") or "").strip() or str(uuid.uuid4())
    name = str(payload.get("name") or "").strip()
    description = str(payload.get("description") or name).strip()
    full_request = _strip_code_hash(
        _attach_builtin_source_snapshot(payload.get("request") or {})
    )
    full_result = _strip_code_hash(payload.get("result") or {})
    if not isinstance(full_result, dict):
        full_result = {}
    verified_token = str(
        payload.get("verified_token")
        or payload.get("verifiedToken")
        or full_result.get("_svquant_verified_token")
        or ""
    ).strip()
    verified = verify_result(user_id, full_result, verified_token)
    rhash = result_hash(full_result)
    full_result.pop("_svquant_verified_token", None)
    request = slim_strategy_request(full_request)
    result = slim_strategy_result_for_db(full_result)
    finished_at = payload.get("finishedAt") or payload.get("finished_at")
    elapsed = float(payload.get("elapsedSec") or payload.get("elapsed_sec") or 0)

    # 完整明细先落盘（含全部 rebalance_logs），再写库摘要
    write_run_blob(
        user_id,
        run_id,
        {"request": full_request if isinstance(full_request, dict) else {}, "result": full_result},
    )

    with get_conn() as conn:
        proj = conn.execute(
            "SELECT id, name FROM strategy_projects WHERE user_id = %s AND id = %s",
            (user_id, project_id),
        ).fetchone()
        if not proj:
            raise KeyError(f"project:{project_id}")
        if not name:
            name = proj["name"] or "策略回测"
        req_json = _dumps(request)
        res_json = _dumps(result)
        row = conn.execute(
            """
            INSERT INTO strategy_runs
              (id, user_id, project_id, name, description, request, result, finished_at, elapsed_sec, verified, result_hash)
            VALUES (
              %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
              COALESCE(%s::timestamptz, NOW()), %s, %s, %s
            )
            ON CONFLICT (user_id, id) DO UPDATE SET
              request = EXCLUDED.request,
              result = EXCLUDED.result,
              finished_at = EXCLUDED.finished_at,
              elapsed_sec = EXCLUDED.elapsed_sec,
              verified = EXCLUDED.verified,
              result_hash = EXCLUDED.result_hash
            RETURNING *
            """,
            (
                run_id,
                user_id,
                project_id,
                name,
                description,
                req_json,
                res_json,
                finished_at,
                elapsed,
                bool(verified),
                rhash,
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
    run = _row_run(dict(row))
    run["result"] = full_result
    return {
        "ok": True,
        "user_id": int(user_id),
        "run": run,
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
    delete_run_blob(user_id, run_id)
    return {"ok": True, "id": run_id}
