# -*- coding: utf-8 -*-
"""PostgreSQL 连接（SVQuant 产品持久化数据）。"""
from __future__ import annotations

from contextlib import contextmanager
import queue
import sys
import threading
from typing import Iterator
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from services.core.env_config import env

DEFAULT_URL = "postgresql://svquant:svquant_local@127.0.0.1:5432/svquant"
_POOLS: dict[bool, "queue.LifoQueue[psycopg.Connection]"] = {}
_POOL_COUNTS: dict[bool, int] = {}
_POOL_LOCK = threading.Lock()


def _running_under_pytest() -> bool:
    return any(name == "pytest" or name.startswith("_pytest") for name in sys.modules)


def _assert_test_database(url: str) -> None:
    """pytest 进程禁止连接生产库，避免测试建表/写数据污染 svquant。"""
    if not _running_under_pytest():
        return
    name = urlparse(url).path.lstrip("/").split("/")[0]
    safe = (
        name.endswith("_test")
        or name.endswith("_dev")
        or name.endswith("_ci")
        or name.endswith("_e2e")
        or name.endswith("_local")
        or "_test" in name
        or "_dev" in name
        or "_e2e" in name
    )
    if name and not safe:
        raise RuntimeError(
            f"测试拒绝连接数据库 {name}：请使用 svquant_test / svquant_dev / *_ci，"
            "不要把 backend/.env 指向生产 svquant。"
        )


def database_url() -> str:
    url = env("DATABASE_URL", DEFAULT_URL) or DEFAULT_URL
    _assert_test_database(url)
    return url


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
            try:
                return _new_conn(autocommit=autocommit)
            except Exception:
                _POOL_COUNTS[autocommit] = count
                raise
    try:
        conn = _POOLS[autocommit].get(timeout=10)
    except queue.Empty:
        # 池满且无空闲：临时超限借出，归还时由 _return_conn 回收
        conn = _new_conn(autocommit=autocommit)
        with _POOL_LOCK:
            _POOL_COUNTS[autocommit] = _POOL_COUNTS.get(autocommit, 0) + 1
        return conn
    if conn.closed:
        # 池内连接已失效（如数据库重启），沿用原计数额度重建
        try:
            return _new_conn(autocommit=autocommit)
        except Exception:
            with _POOL_LOCK:
                _POOL_COUNTS[autocommit] = max(0, _POOL_COUNTS.get(autocommit, 0) - 1)
            raise
    return conn


def _return_conn(conn: psycopg.Connection, *, autocommit: bool) -> None:
    with _POOL_LOCK:
        count = _POOL_COUNTS.get(autocommit, 0)
        if conn.closed or count > _pool_size():
            # 失效连接或超限临时连接：关闭并回收计数额度
            _POOL_COUNTS[autocommit] = max(0, count - 1)
        else:
            _POOLS.setdefault(autocommit, queue.LifoQueue()).put(conn)
            return
    try:
        conn.close()
    except Exception:
        pass


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
