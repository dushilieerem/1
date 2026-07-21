# -*- coding: utf-8 -*-
"""PostgreSQL 连接（社区 / 账号）。面板 metrics 仍用 SQLite。"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from services.env_config import env

DEFAULT_URL = "postgresql://svquant:svquant_local@127.0.0.1:5432/svquant"


def database_url() -> str:
    return env("DATABASE_URL", DEFAULT_URL) or DEFAULT_URL


@contextmanager
def get_conn(*, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(database_url(), row_factory=dict_row, autocommit=autocommit)
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.close()
