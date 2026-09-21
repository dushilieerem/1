# -*- coding: utf-8 -*-
"""因子面板指标持久化：PostgreSQL 真源与旧 SQLite 一次性导入。"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.core.db import get_conn


LEGACY_SQLITE_PATH = (
    Path(__file__).resolve().parents[2]
    / "output"
    / "factor_dashboard"
    / "metrics.sqlite"
)
MIGRATION_KEY = "factor_dashboard_metrics_from_sqlite_v1"
_migration_lock = threading.Lock()
_schema_lock = threading.Lock()
_migration_done = False
_schema_done = False

METRIC_COLUMNS = (
    "factor_name",
    "library",
    "universe",
    "period",
    "filter_limit_up",
    "filter_suspended",
    "rules_version",
    "name_cn",
    "ic_mean",
    "ic_std",
    "ir",
    "rank_ic",
    "q1_return",
    "q5_return",
    "long_short_spread",
    "q1_turnover",
    "q5_turnover",
    "coverage_pool",
    "coverage_total",
    "win_rate",
    "volatility",
    "sharpe",
    "annual_return",
    "max_drawdown",
    "error",
    "computed_at",
)
_UPSERT_SQL = """\
INSERT INTO factor_dashboard_metrics ({columns})
VALUES ({placeholders})
ON CONFLICT (
    factor_name, library, universe, period,
    filter_limit_up, filter_suspended, rules_version
)
DO UPDATE SET {updates}
WHERE factor_dashboard_metrics.computed_at < EXCLUDED.computed_at
"""


def ensure_factor_dashboard_metrics_schema() -> None:
    """创建 PostgreSQL 指标缓存及旧库迁移标记表。"""
    global _schema_done
    if _schema_done:
        return
    with _schema_lock:
        if _schema_done:
            return
        with get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS factor_dashboard_metrics (
                  factor_name TEXT NOT NULL,
                  library TEXT NOT NULL DEFAULT '',
                  universe TEXT NOT NULL,
                  period TEXT NOT NULL,
                  filter_limit_up SMALLINT NOT NULL CHECK (filter_limit_up IN (0, 1)),
                  filter_suspended SMALLINT NOT NULL CHECK (filter_suspended IN (0, 1)),
                  rules_version TEXT NOT NULL DEFAULT 'yg_v1',
                  name_cn TEXT,
                  ic_mean DOUBLE PRECISION,
                  ic_std DOUBLE PRECISION,
                  ir DOUBLE PRECISION,
                  rank_ic DOUBLE PRECISION,
                  q1_return DOUBLE PRECISION,
                  q5_return DOUBLE PRECISION,
                  long_short_spread DOUBLE PRECISION,
                  q1_turnover DOUBLE PRECISION,
                  q5_turnover DOUBLE PRECISION,
                  coverage_pool DOUBLE PRECISION,
                  coverage_total DOUBLE PRECISION,
                  win_rate DOUBLE PRECISION,
                  volatility DOUBLE PRECISION,
                  sharpe DOUBLE PRECISION,
                  annual_return DOUBLE PRECISION,
                  max_drawdown DOUBLE PRECISION,
                  error TEXT,
                  computed_at TIMESTAMPTZ NOT NULL,
                  PRIMARY KEY (
                    factor_name, library, universe, period,
                    filter_limit_up, filter_suspended, rules_version
                  )
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_factor_dashboard_metrics_query
                ON factor_dashboard_metrics
                  (universe, period, filter_limit_up, filter_suspended,
                   rules_version, library, factor_name)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS factor_dashboard_legacy_imports (
                  migration_key TEXT PRIMARY KEY,
                  source_rows BIGINT NOT NULL DEFAULT 0,
                  imported_rows BIGINT NOT NULL DEFAULT 0,
                  skipped_rows BIGINT NOT NULL DEFAULT 0,
                  completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        _schema_done = True


def _parse_timestamp(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        parsed = raw
    else:
        value = str(raw or "").strip()
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _upsert_sql() -> str:
    columns = ", ".join(METRIC_COLUMNS)
    placeholders = ", ".join("%s" for _ in METRIC_COLUMNS)
    key_columns = {
        "factor_name",
        "library",
        "universe",
        "period",
        "filter_limit_up",
        "filter_suspended",
        "rules_version",
    }
    updates = ", ".join(
        f"{column} = EXCLUDED.{column}"
        for column in METRIC_COLUMNS
        if column not in key_columns
    )
    return _UPSERT_SQL.format(
        columns=columns,
        placeholders=placeholders,
        updates=updates,
    )


def _legacy_table_columns(conn: sqlite3.Connection) -> set[str] | None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        ("factor_dashboard_metrics",),
    ).fetchone()
    if exists is None:
        return None
    return {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(factor_dashboard_metrics)")
    }


def _import_legacy_factor_dashboard_metrics(conn: Any) -> dict[str, int]:
    zero_result = {"source_rows": 0, "imported_rows": 0, "skipped_rows": 0}
    if not LEGACY_SQLITE_PATH.is_file():
        return zero_result

    sqlite_uri = f"file:{LEGACY_SQLITE_PATH.as_posix()}?mode=ro"
    sqlite_conn = sqlite3.connect(sqlite_uri, uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    try:
        columns = _legacy_table_columns(sqlite_conn)
        if columns is None:
            return zero_result
        required = {
            "factor_name",
            "universe",
            "period",
            "filter_limit_up",
            "filter_suspended",
            "computed_at",
        }
        if not required.issubset(columns):
            raise RuntimeError("旧因子指标缓存字段不完整，已停止迁移以避免丢失记录")

        select_columns = [column for column in METRIC_COLUMNS if column in columns]
        sqlite_cursor = sqlite_conn.execute(
            f"SELECT {', '.join(select_columns)} FROM factor_dashboard_metrics"
        )
        source_rows = imported_rows = skipped_rows = 0
        upsert_sql = _upsert_sql()
        while batch := sqlite_cursor.fetchmany(500):
            values: list[tuple[Any, ...]] = []
            for source in batch:
                row = dict(source)
                source_rows += 1
                factor_name = str(row.get("factor_name") or "").strip()
                universe = str(row.get("universe") or "").strip()
                period = str(row.get("period") or "").strip()
                try:
                    filter_limit_up = int(row.get("filter_limit_up"))
                    filter_suspended = int(row.get("filter_suspended"))
                except (TypeError, ValueError):
                    skipped_rows += 1
                    continue
                if (
                    not factor_name
                    or not universe
                    or not period
                    or filter_limit_up not in (0, 1)
                    or filter_suspended not in (0, 1)
                ):
                    skipped_rows += 1
                    continue

                normalized = {
                    **row,
                    "factor_name": factor_name,
                    "library": str(row.get("library") or "").strip(),
                    "universe": universe,
                    "period": period,
                    "filter_limit_up": filter_limit_up,
                    "filter_suspended": filter_suspended,
                    "rules_version": str(row.get("rules_version") or "yg_v1"),
                    "computed_at": _parse_timestamp(row.get("computed_at")),
                }
                values.append(
                    tuple(normalized.get(column) for column in METRIC_COLUMNS)
                )

            if values:
                cursor = conn.cursor()
                cursor.executemany(upsert_sql, values)
                imported_rows += max(cursor.rowcount, 0)

        conn.execute(
            """
            INSERT INTO factor_dashboard_legacy_imports
              (migration_key, source_rows, imported_rows, skipped_rows)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (migration_key) DO NOTHING
            """,
            (MIGRATION_KEY, source_rows, imported_rows, skipped_rows),
        )
        return {
            "source_rows": source_rows,
            "imported_rows": imported_rows,
            "skipped_rows": skipped_rows,
        }
    finally:
        sqlite_conn.close()


def migrate_legacy_factor_dashboard_metrics() -> dict[str, int]:
    """将旧 SQLite 指标缓存幂等导入 PostgreSQL；成功后记录一次性迁移标记。

    旧文件只以只读模式打开，且不会被删除或修改。冲突时仅当源缓存时间更新，
    才覆盖 PostgreSQL 中同一配置的缓存行；完成后由 PostgreSQL 标记避免再次读取 SQLite。
    """
    global _migration_done
    zero_result = {"source_rows": 0, "imported_rows": 0, "skipped_rows": 0}
    if _migration_done:
        return zero_result

    with _migration_lock:
        if _migration_done:
            return zero_result
        ensure_factor_dashboard_metrics_schema()
        with get_conn() as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (MIGRATION_KEY,),
            )
            marker = conn.execute(
                """
                SELECT 1
                FROM factor_dashboard_legacy_imports
                WHERE migration_key = %s
                """,
                (MIGRATION_KEY,),
            ).fetchone()
            result = (
                zero_result
                if marker is not None
                else _import_legacy_factor_dashboard_metrics(conn)
            )

        _migration_done = True
        return result


__all__ = [
    "ensure_factor_dashboard_metrics_schema",
    "migrate_legacy_factor_dashboard_metrics",
]
