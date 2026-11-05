# -*- coding: utf-8 -*-
"""连接池硬上限：池满等待/有限超限，绝不无限建连。"""
from __future__ import annotations

import queue

import pytest

from services.core import db


class FakeConn:
    def __init__(self) -> None:
        self.autocommit = False
        self.closed = False
        self.commits = 0
        self.rollbacks = 0
        self.closed_calls = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True
        self.closed_calls += 1


@pytest.fixture(autouse=True)
def isolated_pool(monkeypatch):
    monkeypatch.setattr(db, "_POOL", queue.LifoQueue())
    monkeypatch.setattr(db, "_POOL_COUNT", 0)
    monkeypatch.setattr(db, "_pool_size", lambda: 1)
    monkeypatch.setattr(db, "_pool_overflow", lambda: 0)
    monkeypatch.setattr(db, "_pool_wait_sec", lambda: 0.01)
    yield


def test_reuses_connection_and_switches_autocommit(monkeypatch):
    created: list[FakeConn] = []

    def new_conn(*, autocommit: bool) -> FakeConn:
        conn = FakeConn()
        conn.autocommit = autocommit
        created.append(conn)
        return conn

    monkeypatch.setattr(db, "_new_conn", new_conn)
    with db.get_conn() as first:
        assert first.autocommit is False
        assert first.commits == 0
    assert db._POOL.qsize() == 1

    with db.get_conn(autocommit=True) as second:
        assert second is first
        assert second.autocommit is True
    assert len(created) == 1


def test_pool_full_raises_busy_instead_of_unbounded_connect(monkeypatch):
    monkeypatch.setattr(db, "_new_conn", lambda *, autocommit: FakeConn())
    first = db._borrow_conn(autocommit=False)
    with pytest.raises(db.DatabasePoolBusy):
        db._borrow_conn(autocommit=False)
    db._return_conn(first, autocommit=False)
    assert db._POOL.qsize() == 1


def test_overflow_is_bounded_and_closed_on_return(monkeypatch):
    monkeypatch.setattr(db, "_pool_overflow", lambda: 1)
    monkeypatch.setattr(db, "_new_conn", lambda *, autocommit: FakeConn())
    first = db._borrow_conn(autocommit=False)
    second = db._borrow_conn(autocommit=False)
    assert second is not first
    assert db._POOL_COUNT == 2
    db._return_conn(second, autocommit=False)
    assert second.closed is True
    assert db._POOL_COUNT == 1
    db._return_conn(first, autocommit=False)
    assert db._POOL.qsize() == 1


def test_failed_connect_releases_slot(monkeypatch):
    def fail(*, autocommit: bool):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "_new_conn", fail)
    with pytest.raises(RuntimeError):
        db._borrow_conn(autocommit=False)
    assert db._POOL_COUNT == 0


def test_context_rolls_back_on_error(monkeypatch):
    monkeypatch.setattr(db, "_new_conn", lambda *, autocommit: FakeConn())
    conn = None
    with pytest.raises(ValueError):
        with db.get_conn() as borrowed:
            conn = borrowed
            raise ValueError("boom")
    assert conn is not None
    assert conn.rollbacks == 1
    assert conn.commits == 0
