# -*- coding: utf-8 -*-
"""PostgreSQL 连接（SVQuant 产品持久化数据）。"""
from __future__ import annotations

from contextlib import contextmanager
import queue
import threading
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from services.core.env_config import env

DEFAULT_URL = "postgresql://svquant:svquant_local@127.0.0.1:5432/svquant"
_POOLS: dict[bool, "queue.LifoQueue[psycopg.Connection]"] = {}
_POOL_COUNTS: dict[bool, int] = {}
_POOL_LOCK = threading.Lock()


def database_url() -> str:
    return env("DATABASE_URL", DEFAULT_URL) or DEFAULT_URL


def _pool_size() -> int:
    try:
        return max(1, min(100, int(env("SVQUANT_DB_POOL_SIZE", "20") or "20")))
    except (TypeError, ValueError):
        return 20


def _new_conn(*, autocommit: bool) -> psycopg.Connection:
    return psycopg.connect(database_url(), row_factory=dict_row, autocommit=autocommit)


def _borrow_conn(*, autocommit: bool) -> psycopg.Connection:
    with _POOL_LOCK:
        pool = _POOLS.setdefault(autocommit, queue.LifoQueue())
        count = _POOL_COUNTS.get(autocommit, 0)
        if count < _pool_size():
            _POOL_COUNTS[autocommit] = count + 1
            return _new_conn(autocommit=autocommit)
    try:
        conn = _POOLS[autocommit].get(timeout=10)
    except queue.Empty:
        return _new_conn(autocommit=autocommit)
    if conn.closed:
        return _new_conn(autocommit=autocommit)
    return conn


def _return_conn(conn: psycopg.Connection, *, autocommit: bool) -> None:
    if conn.closed:
        with _POOL_LOCK:
            _POOL_COUNTS[autocommit] = max(0, _POOL_COUNTS.get(autocommit, 0) - 1)
        return
    _POOLS.setdefault(autocommit, queue.LifoQueue()).put(conn)


@contextmanager
def get_conn(*, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    conn = _borrow_conn(autocommit=autocommit)
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        _return_conn(conn, autocommit=autocommit)
