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
# 单一连接池：借出时切换 autocommit，避免按模式各开一份池导致总连接数翻倍。
_POOL: "queue.LifoQueue[psycopg.Connection]" = queue.LifoQueue()
_POOL_COUNT = 0
_POOL_LOCK = threading.Lock()


class DatabasePoolBusy(RuntimeError):
    """连接池达到硬上限，请求应快速失败而不是继续压垮 PostgreSQL。"""


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


def _pool_overflow() -> int:
    """池满后允许的短时超限连接数；默认 5，设为 0 表示池满直接 503。"""
    try:
        return max(0, min(100, int(env("SVQUANT_DB_POOL_OVERFLOW", "5") or "5")))
    except (TypeError, ValueError):
        return 5


def _pool_wait_sec() -> float:
    try:
        return max(0.1, min(60.0, float(env("SVQUANT_DB_POOL_WAIT_SEC", "10") or "10")))
    except (TypeError, ValueError):
        return 10.0


def _new_conn(*, autocommit: bool) -> psycopg.Connection:
    return psycopg.connect(database_url(), row_factory=dict_row, autocommit=autocommit)


def _take_idle(*, autocommit: bool) -> psycopg.Connection | None:
    """先复用空闲连接；失效连接回收计数后继续找。"""
    global _POOL_COUNT
    while True:
        try:
            conn = _POOL.get_nowait()
        except queue.Empty:
            return None
        if not conn.closed:
            conn.autocommit = autocommit
            return conn
        with _POOL_LOCK:
            _POOL_COUNT = max(0, _POOL_COUNT - 1)


def _create_slot(*, autocommit: bool) -> psycopg.Connection | None:
    """在硬上限内占用一个槽位并建连；返回 None 表示达到上限。"""
    global _POOL_COUNT
    with _POOL_LOCK:
        if _POOL_COUNT >= _pool_size() + _pool_overflow():
            return None
        _POOL_COUNT += 1
    try:
        return _new_conn(autocommit=autocommit)
    except Exception:
        with _POOL_LOCK:
            _POOL_COUNT = max(0, _POOL_COUNT - 1)
        raise


def _borrow_conn(*, autocommit: bool) -> psycopg.Connection:
    conn = _take_idle(autocommit=autocommit)
    if conn is not None:
        return conn

    conn = _create_slot(autocommit=autocommit)
    if conn is not None:
        return conn

    # 池已满：短暂等待归还，仍无空闲才允许有限超限，绝不无限建连。
    try:
        conn = _POOL.get(timeout=_pool_wait_sec())
    except queue.Empty:
        conn = None
    if conn is not None:
        if not conn.closed:
            conn.autocommit = autocommit
            return conn
        with _POOL_LOCK:
            _POOL_COUNT = max(0, _POOL_COUNT - 1)

    conn = _create_slot(autocommit=autocommit)
    if conn is not None:
        return conn
    raise DatabasePoolBusy(
        f"数据库连接池繁忙（上限 {_pool_size()}+{_pool_overflow()}），请稍后重试"
    )


def _return_conn(conn: psycopg.Connection, *, autocommit: bool) -> None:
    _ = autocommit
    global _POOL_COUNT
    if conn.closed:
        with _POOL_LOCK:
            _POOL_COUNT = max(0, _POOL_COUNT - 1)
        return
    with _POOL_LOCK:
        if _POOL_COUNT > _pool_size():
            _POOL_COUNT = max(0, _POOL_COUNT - 1)
            close = True
        else:
            _POOL.put(conn)
            return
    if close:
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
