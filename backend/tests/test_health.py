# -*- coding: utf-8 -*-
"""健康检查：DB/schema 可用时必须返回 ok，并带连接池字段。"""
from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_health_returns_ok_and_pool_fields() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["db"] == "ok"
    assert body.get("schema")
    assert body["db_pool"]["limit"] >= body["db_pool"]["used"] >= 0
