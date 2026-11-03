# -*- coding: utf-8 -*-
"""测试进程禁止连接生产库。"""
from __future__ import annotations

import pytest

from services.core import db


def test_pytest_rejects_production_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://svquant:secret@127.0.0.1:5432/svquant")
    with pytest.raises(RuntimeError, match="拒绝连接数据库 svquant"):
        db.database_url()


def test_pytest_allows_test_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://svquant:secret@127.0.0.1:5432/svquant_test")
    assert db.database_url().endswith("/svquant_test")


def test_pytest_allows_dev_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://svquant:secret@127.0.0.1:5432/svquant_dev")
    assert db.database_url().endswith("/svquant_dev")
