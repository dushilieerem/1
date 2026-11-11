# -*- coding: utf-8 -*-
"""迁移登记表 schema 选择：避免 search_path 在迁移中途建 svquant schema 后翻转。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.core import migrations as M  # noqa: E402


class _Result:
    def __init__(self, row: dict) -> None:
        self._row = row

    def fetchone(self) -> dict:
        return self._row


class _FakeConn:
    """只实现 _pick_registry_schema 用到的两条查询。"""

    def __init__(self, existing: dict[str, int]) -> None:
        self.existing = existing
        self.statements: list[str] = []

    def execute(self, sql: str, params: tuple | None = None) -> _Result:
        self.statements.append(sql)
        if "to_regclass" in sql:
            name = str((params or ("",))[0])
            return _Result({"ok": name.split(".")[0] in self.existing})
        if "COUNT(*)" in sql:
            # SELECT COUNT(*) AS n FROM <schema>.schema_migrations
            schema = sql.split("FROM ")[1].split(".")[0].strip()
            return _Result({"n": self.existing[schema]})
        return _Result({})  # CREATE TABLE ...


def test_fresh_database_uses_public() -> None:
    assert M._pick_registry_schema(_FakeConn({})) == "public"


def test_existing_rows_win_regardless_of_schema_order() -> None:
    # 生产：登记行在 svquant
    assert M._pick_registry_schema(_FakeConn({"svquant": 37, "public": 0})) == "svquant"
    # 空库门禁跑完：登记行在 public
    assert M._pick_registry_schema(_FakeConn({"svquant": 0, "public": 37})) == "public"


def test_both_empty_prefers_svquant() -> None:
    assert M._pick_registry_schema(_FakeConn({"svquant": 0, "public": 0})) == "svquant"
    assert M._pick_registry_schema(_FakeConn({"public": 0})) == "public"


def test_qualified_statements_never_use_bare_table_name() -> None:
    conn = _FakeConn({})
    schema = M._ensure_table(conn)
    assert schema == "public"
    assert "public.schema_migrations" in conn.statements[-1]
    assert "FROM schema_migrations" not in conn.statements[-1]
