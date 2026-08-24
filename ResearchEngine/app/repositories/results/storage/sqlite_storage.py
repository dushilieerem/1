"""``SQLiteStorage`` - 以 SQLite 数据库保存结果。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.repositories.results.storage.base import ResultStorage


class SQLiteStorage(ResultStorage):
    """把结果写入单个 SQLite 文件。

    - 表 ``metrics(name TEXT, value REAL)``
    - 表 ``artifacts(name TEXT, data TEXT)`` 存 equity_curve / factor_values /
      positions 的 JSON 序列化
    - 表 ``meta(key TEXT, value TEXT)``
    """

    name = "sqlite"

    def _connect(self, path: str) -> sqlite3.Connection:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(p))

    def write(self, result, path: str) -> None:
        conn = self._connect(path)
        try:
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS metrics")
            cur.execute("DROP TABLE IF EXISTS artifacts")
            cur.execute("DROP TABLE IF EXISTS meta")
            cur.execute("CREATE TABLE metrics (name TEXT, value REAL)")
            cur.execute("CREATE TABLE artifacts (name TEXT, data TEXT)")
            cur.execute("CREATE TABLE meta (key TEXT, value TEXT)")

            cur.executemany(
                "INSERT INTO metrics VALUES (?, ?)",
                list(result.metrics.items()),
            )
            cur.executemany(
                "INSERT INTO artifacts VALUES (?, ?)",
                list(self._artifacts(result).items()),
            )
            cur.execute(
                "INSERT INTO meta VALUES (?, ?)",
                ("meta", json.dumps(result.meta, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    def read(self, path: str):
        from app.repositories.results.manager import ResultManager

        conn = self._connect(path)
        result = ResultManager(storage=self)
        try:
            cur = conn.cursor()
            cur.execute("SELECT name, value FROM metrics")
            result.metrics = {row[0]: float(row[1]) for row in cur.fetchall()}

            cur.execute("SELECT name, data FROM artifacts")
            self._apply_artifacts(result, {row[0]: row[1] for row in cur.fetchall()})

            cur.execute("SELECT value FROM meta WHERE key='meta'")
            row = cur.fetchone()
            if row:
                result.meta = json.loads(row[0])
        finally:
            conn.close()
        return result
