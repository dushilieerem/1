# -*- coding: utf-8 -*-
"""psycopg 连接的 SQLite 占位符兼容包装。

`rules.py` 从 invest-api 迁移而来，查询里仍是 `?` 占位符；这里只做 `? -> %s`
的替换，不改变 SQL 语义。新代码优先直接写 `%s`。
"""
from __future__ import annotations

import re
from typing import Any, Iterator

from services.core.db import get_conn


# SQL 里可能有 LIKE 'doc-%' 这类字面量百分号；psycopg 只认 %s/%b/%t 占位符，
# 需要把其余 % 转义为 %%，否则 News/Topic 接口会 500。
_PERCENT_LITERAL_RE = re.compile(r"%(?![sbt%])")


def pg_sql(sql: str) -> str:
    return _PERCENT_LITERAL_RE.sub("%%", sql.replace("?", "%s"))


class PGConn:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Any = ()) -> Any:
        return self._conn.execute(pg_sql(sql), tuple(params))

    def commit(self) -> None:
        self._conn.commit()

    @property
    def raw(self) -> Any:
        return self._conn


def invest_conn() -> Iterator[PGConn]:
    with get_conn() as conn:
        yield PGConn(conn)


__all__ = ["PGConn", "invest_conn"]
