"""因子批量回测的 SQLite 结果仓库。

该仓库只保存批次、状态和标量指标，不保存净值曲线或日频序列。
它与 ``ResultStorage`` 分离，后者仍负责单次实验快照。
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


METRIC_COLUMNS = (
    "annual_return",
    "volatility",
    "sharpe",
    "max_drawdown",
    "annual_excess_return",
    "excess_volatility",
    "information_ratio",
    "benchmark_win_rate",
)


def default_factor_backtest_db_path() -> Path:
    """返回因子批量指标库路径，可由环境变量覆盖。"""

    configured = (
        os.environ.get("SVQUANT_FACTOR_BACKTEST_DB")
        or os.environ.get("SVQUANT_FACTOR_BACKTEST_DB_PATH")
    )
    if configured:
        return Path(configured)
    from app.repositories.catalogs.paths import _repo_root

    return _repo_root() / "Factor" / "database" / "factor_backtest.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class FactorBacktestStore:
    """因子批量回测批次与标量指标的持久化服务。"""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else default_factor_backtest_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _initialize(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS batch_runs (
                    id TEXT PRIMARY KEY,
                    batch_key TEXT NOT NULL UNIQUE,
                    as_of_date TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    profile_hash TEXT NOT NULL,
                    catalog_version TEXT NOT NULL,
                    metric_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_count INTEGER NOT NULL DEFAULT 0,
                    succeeded_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT,
                    finished_at TEXT,
                    supersedes_batch_id TEXT REFERENCES batch_runs(id),
                    error_code TEXT,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS factor_runs (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL REFERENCES batch_runs(id) ON DELETE CASCADE,
                    library_name TEXT NOT NULL,
                    factor_name TEXT NOT NULL,
                    factor_source_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    error_message TEXT,
                    actual_start TEXT,
                    actual_end TEXT,
                    observation_days INTEGER,
                    sample_quality TEXT,
                    elapsed_seconds REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(batch_id, library_name, factor_name)
                );

                CREATE TABLE IF NOT EXISTS factor_quantile_metrics (
                    factor_run_id TEXT NOT NULL REFERENCES factor_runs(id) ON DELETE CASCADE,
                    quantile TEXT NOT NULL,
                    annual_return REAL,
                    volatility REAL,
                    sharpe REAL,
                    max_drawdown REAL,
                    annual_excess_return REAL,
                    excess_volatility REAL,
                    information_ratio REAL,
                    benchmark_win_rate REAL,
                    PRIMARY KEY(factor_run_id, quantile)
                );

                CREATE TABLE IF NOT EXISTS factor_predictive_metrics (
                    factor_run_id TEXT PRIMARY KEY REFERENCES factor_runs(id) ON DELETE CASCADE,
                    ic_mean REAL,
                    rank_ic_mean REAL,
                    ic_ir REAL
                );

                CREATE INDEX IF NOT EXISTS idx_batch_runs_as_of
                    ON batch_runs(as_of_date DESC);
                CREATE INDEX IF NOT EXISTS idx_factor_runs_batch_status
                    ON factor_runs(batch_id, status);
                CREATE INDEX IF NOT EXISTS idx_factor_runs_factor_history
                    ON factor_runs(library_name, factor_name, created_at DESC);
                """
            )
            # 允许从 MVP 早期创建的数据库平滑升级到带基础设施错误信息的表。
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(batch_runs)").fetchall()
            }
            for name in ("error_code", "error_message"):
                if name not in columns:
                    conn.execute(f"ALTER TABLE batch_runs ADD COLUMN {name} TEXT")
            conn.commit()
        finally:
            conn.close()

    def get_batch_by_key(self, batch_key: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM batch_runs WHERE batch_key = ?", (batch_key,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_batch(
        self,
        *,
        batch_key: str,
        as_of_date: str,
        window_start: str,
        window_end: str,
        profile: dict[str, Any],
        profile_hash: str,
        catalog_version: str,
        metric_version: str,
        total_count: int,
        supersedes_batch_id: str | None = None,
    ) -> dict[str, Any]:
        batch_id = uuid.uuid4().hex
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO batch_runs (
                    id, batch_key, as_of_date, window_start, window_end,
                    profile_json, profile_hash, catalog_version, metric_version,
                    status, total_count, supersedes_batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    batch_id,
                    batch_key,
                    as_of_date,
                    window_start,
                    window_end,
                    _json(profile),
                    profile_hash,
                    catalog_version,
                    metric_version,
                    total_count,
                    supersedes_batch_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_batch(batch_id)  # type: ignore[return-value]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM batch_runs WHERE id = ?", (batch_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def mark_batch_running(self, batch_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE batch_runs SET status = 'running', started_at = COALESCE(started_at, ?) WHERE id = ?",
                (_now(), batch_id),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_batch_failed(
        self,
        batch_id: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE batch_runs SET status = 'failed', finished_at = ?,
                    error_code = ?, error_message = ?
                WHERE id = ?
                """,
                (_now(), error_code, error_message, batch_id),
            )
            conn.commit()
        finally:
            conn.close()

    def ensure_factor_run(
        self,
        *,
        batch_id: str,
        library_name: str,
        factor_name: str,
        factor_source_hash: str,
    ) -> dict[str, Any]:
        now = _now()
        factor_id = uuid.uuid4().hex
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO factor_runs (
                    id, batch_id, library_name, factor_name, factor_source_hash,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (factor_id, batch_id, library_name, factor_name, factor_source_hash, now, now),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT * FROM factor_runs
                WHERE batch_id = ? AND library_name = ? AND factor_name = ?
                """,
                (batch_id, library_name, factor_name),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def mark_factor_running(self, factor_run_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE factor_runs SET status = 'running', updated_at = ? WHERE id = ?",
                (_now(), factor_run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def record_factor(
        self,
        factor_run_id: str,
        *,
        status: str,
        retry_count: int = 0,
        error_code: str | None = None,
        error_message: str | None = None,
        actual_start: str | None = None,
        actual_end: str | None = None,
        observation_days: int | None = None,
        sample_quality: str | None = None,
        elapsed_seconds: float | None = None,
        quantile_metrics: Iterable[dict[str, Any]] = (),
        predictive_metrics: dict[str, Any] | None = None,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE factor_runs SET
                    status = ?, retry_count = ?, error_code = ?, error_message = ?,
                    actual_start = ?, actual_end = ?, observation_days = ?,
                    sample_quality = ?, elapsed_seconds = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    retry_count,
                    error_code,
                    error_message,
                    actual_start,
                    actual_end,
                    observation_days,
                    sample_quality,
                    _finite(elapsed_seconds),
                    _now(),
                    factor_run_id,
                ),
            )
            conn.execute("DELETE FROM factor_quantile_metrics WHERE factor_run_id = ?", (factor_run_id,))
            for row in quantile_metrics:
                conn.execute(
                    """
                    INSERT INTO factor_quantile_metrics (
                        factor_run_id, quantile, annual_return, volatility, sharpe,
                        max_drawdown, annual_excess_return, excess_volatility,
                        information_ratio, benchmark_win_rate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        factor_run_id,
                        str(row.get("quantile")),
                        *(_finite(row.get(column)) for column in METRIC_COLUMNS),
                    ),
                )
            conn.execute("DELETE FROM factor_predictive_metrics WHERE factor_run_id = ?", (factor_run_id,))
            if predictive_metrics is not None:
                conn.execute(
                    """
                    INSERT INTO factor_predictive_metrics (factor_run_id, ic_mean, rank_ic_mean, ic_ir)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        factor_run_id,
                        _finite(predictive_metrics.get("ic_mean")),
                        _finite(predictive_metrics.get("rank_ic_mean")),
                        _finite(predictive_metrics.get("ic_ir")),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def refresh_batch_counts(self, batch_id: str, *, final: bool = False) -> dict[str, Any]:
        conn = self._connect()
        try:
            counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(status = 'succeeded') AS succeeded,
                    SUM(status = 'failed') AS failed,
                    SUM(status = 'skipped') AS skipped
                FROM factor_runs WHERE batch_id = ?
                """,
                (batch_id,),
            ).fetchone()
            total = int(counts["total"] or 0)
            succeeded = int(counts["succeeded"] or 0)
            failed = int(counts["failed"] or 0)
            skipped = int(counts["skipped"] or 0)
            complete = total > 0 and succeeded + failed + skipped == total
            status = "completed" if final and complete else "running"
            conn.execute(
                """
                UPDATE batch_runs SET status = ?, total_count = ?, succeeded_count = ?,
                    failed_count = ?, skipped_count = ?, finished_at = CASE WHEN ? THEN ? ELSE finished_at END
                WHERE id = ?
                """,
                (status, total, succeeded, failed, skipped, int(final and complete), _now(), batch_id),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_batch(batch_id)  # type: ignore[return-value]

    def list_batches(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        as_of_date: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if as_of_date:
            where.append("as_of_date = ?")
            params.append(as_of_date)
        if status:
            where.append("status = ?")
            params.append(status)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        conn = self._connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM batch_runs {clause} ORDER BY as_of_date DESC, started_at DESC LIMIT ? OFFSET ?",
                (*params, max(1, min(limit, 500)), max(0, offset)),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_factor_runs(
        self,
        batch_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        library_name: str | None = None,
        factor_name: str | None = None,
    ) -> list[dict[str, Any]]:
        where = ["f.batch_id = ?"]
        params: list[Any] = [batch_id]
        for field, value in (("f.status", status), ("f.library_name", library_name), ("f.factor_name", factor_name)):
            if value:
                where.append(f"{field} = ?")
                params.append(value)
        conn = self._connect()
        try:
            rows = conn.execute(
                f"""
                SELECT f.*, p.ic_mean, p.rank_ic_mean, p.ic_ir
                FROM factor_runs f
                LEFT JOIN factor_predictive_metrics p ON p.factor_run_id = f.id
                WHERE {' AND '.join(where)}
                ORDER BY f.library_name, f.factor_name
                LIMIT ? OFFSET ?
                """,
                (*params, max(1, min(limit, 1000)), max(0, offset)),
            ).fetchall()
            result = [dict(row) for row in rows]
            for item in result:
                item["quantile_metrics"] = self._quantile_metrics(conn, item["id"])
            return result
        finally:
            conn.close()

    @staticmethod
    def _quantile_metrics(conn: sqlite3.Connection, factor_run_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM factor_quantile_metrics WHERE factor_run_id = ? ORDER BY CASE quantile WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 WHEN 'Q4' THEN 4 WHEN 'Q5' THEN 5 WHEN 'benchmark' THEN 6 ELSE 7 END",
            (factor_run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def factor_history(
        self,
        library_name: str,
        factor_name: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT f.*, b.as_of_date, b.window_start, b.window_end, b.profile_hash,
                       p.ic_mean, p.rank_ic_mean, p.ic_ir
                FROM factor_runs f
                JOIN batch_runs b ON b.id = f.batch_id
                LEFT JOIN factor_predictive_metrics p ON p.factor_run_id = f.id
                WHERE f.library_name = ? AND f.factor_name = ?
                ORDER BY b.as_of_date DESC, f.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (library_name, factor_name, max(1, min(limit, 500)), max(0, offset)),
            ).fetchall()
            result = [dict(row) for row in rows]
            for item in result:
                item["quantile_metrics"] = self._quantile_metrics(conn, item["id"])
            return result
        finally:
            conn.close()


__all__ = ["FactorBacktestStore", "METRIC_COLUMNS", "default_factor_backtest_db_path"]
