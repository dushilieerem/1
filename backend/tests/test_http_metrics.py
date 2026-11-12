# -*- coding: utf-8 -*-
"""HTTP 指标：鉴权、路由模板聚合、请求 ID。"""
from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from services.core import http_metrics  # noqa: E402

client = TestClient(app)


def setup_function() -> None:
    http_metrics.reset()


def test_metrics_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("METRICS_TOKEN", "secret")
    assert client.get("/api/metrics").status_code == 403
    response = client.get("/api/metrics", headers={"X-Metrics-Token": "secret"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "svquant_http_requests_total" in response.text


def test_route_template_and_request_id(monkeypatch) -> None:
    monkeypatch.setenv("METRICS_TOKEN", "secret")
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.headers.get("X-Request-ID")
    text = client.get("/api/metrics", headers={"X-Metrics-Token": "secret"}).text
    assert 'route="/api/health"' in text
    assert 'method="GET"' in text
    assert 'status="200"' in text
    assert "svquant_http_in_flight" in text
    assert "svquant_db_pool_connections" in text


def test_unmatched_route_is_not_raw_path(monkeypatch) -> None:
    monkeypatch.setenv("METRICS_TOKEN", "secret")
    assert client.get("/api/not-a-real-route/12345").status_code == 404
    text = client.get("/api/metrics", headers={"X-Metrics-Token": "secret"}).text
    assert 'route="unmatched"' in text
    assert "/api/not-a-real-route/12345" not in text
