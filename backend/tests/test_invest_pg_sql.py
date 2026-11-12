# -*- coding: utf-8 -*-
"""H5 invest SQL 适配：字面量 % 不能当成 psycopg 占位符。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.invest.db import pg_sql  # noqa: E402


def test_literal_percent_is_escaped() -> None:
    sql = "SELECT * FROM news WHERE id LIKE 'doc-%' OR id LIKE 'news-%'"
    out = pg_sql(sql)
    assert "doc-%%" in out and "news-%%" in out


def test_placeholders_are_preserved() -> None:
    sql = "SELECT * FROM news WHERE kind=? AND id LIKE 'ann-%'"
    out = pg_sql(sql)
    assert "kind=%s" in out
    assert "ann-%%" in out
    assert "%s" in out
