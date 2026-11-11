# -*- coding: utf-8 -*-
"""聚宽策略直跑端点：预检拒绝、异步提交/查询/取消、能力清单。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.deps import require_db_user_id  # noqa: E402
from services.strategy import re_capabilities  # noqa: E402

app.dependency_overrides[require_db_user_id] = lambda: 1
client = TestClient(app)

SAFE_CODE = "def initialize(context):\n    run_daily(trade, time='09:30')\n\ndef trade(context):\n    order_target_percent('600519.XSHG', 0.2)\n"

CAPS = {
    "version": "2026-11-11",
    "dialects": {
        "joinquant": {
            "engine_modes": ["event"],
            "supported_apis": ["order_target_percent"],
            "unsupported_apis": [{"api": "get_call_auction", "reason": "无数据"}],
        }
    },
}


def _caps_forward(_method, _path, **_kwargs):
    return 200, {}, CAPS


def test_precheck_endpoint_blocks_unsupported_api() -> None:
    with patch.object(re_capabilities, "forward_re", _caps_forward), patch.object(
        re_capabilities, "_cached", None
    ):
        re_capabilities.reset_cache()
        resp = client.post("/api/strategy/precheck", json={"code": "def initialize(c):\n    get_call_auction('x')\n"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["can_run_directly"] is False
    assert any(i["code"] == "API-UNSUPPORTED" for i in body["issues"])


def test_joinquant_run_rejects_blocked_code() -> None:
    with patch.object(re_capabilities, "forward_re", _caps_forward):
        re_capabilities.reset_cache()
        resp = client.post(
            "/api/strategy/joinquant/runs",
            json={"code": "def initialize(c):\n    get_call_auction('x')\n", "start": "2024-01-01", "end": "2024-06-30"},
        )
    assert resp.status_code == 400
    body = resp.json()
    error = body.get("error") or (body.get("detail") or {}).get("error")
    assert error == "precheck_failed"
    assert body.get("issues") or (body.get("detail") or {}).get("issues")


def test_joinquant_run_submits_async() -> None:
    calls = {}

    def fake_forward(method, path, **kwargs):
        calls["method"] = method
        calls["path"] = path
        calls["payload"] = kwargs.get("payload")
        return 202, {}, {"run_id": "re-42", "status": "queued"}

    with patch.object(re_capabilities, "forward_re", _caps_forward), patch(
        "app.routers.strategy.forward_re", fake_forward
    ):
        re_capabilities.reset_cache()
        resp = client.post(
            "/api/strategy/joinquant/runs",
            json={"code": SAFE_CODE, "start": "2024-01-01", "end": "2024-06-30", "benchmark": "000300.XSHG"},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] == "re-42"
    assert body["poll_url"] == "/api/strategy/joinquant/runs/re-42"
    assert body["code_hash"]
    assert calls["path"] == "/api/backtest/strategy/async"
    assert calls["payload"]["strategy_dialect"] == "joinquant"
    assert calls["payload"]["engine_mode"] == "event"
    assert calls["payload"]["timed_execution"] is True


def test_joinquant_run_status_and_cancel_proxy() -> None:
    def fake_get(method, path, **kwargs):
        if method == "DELETE":
            return 200, {}, {"run_id": "re-42", "status": "cancelled"}
        return 200, {}, {"run_id": "re-42", "status": "running"}

    with patch("app.routers.strategy.forward_re", fake_get):
        status = client.get("/api/strategy/joinquant/runs/re-42")
        cancel = client.delete("/api/strategy/joinquant/runs/re-42")
    assert status.status_code == 200 and status.json()["status"] == "running"
    assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled"


def test_capabilities_endpoint() -> None:
    with patch.object(re_capabilities, "forward_re", _caps_forward):
        re_capabilities.reset_cache()
        resp = client.get("/api/strategy/capabilities")
    assert resp.status_code == 200
    assert resp.json()["capabilities"]["version"] == "2026-11-11"


def teardown_module(module) -> None:  # noqa: ARG001
    app.dependency_overrides.clear()
    re_capabilities.reset_cache()


def test_run_status_404_distinguishes_expired_and_unknown() -> None:
    def expired(method, path, **kwargs):
        return 404, {}, {"detail": {"status": "expired", "message": "策略任务结果已过期（异步结果保留 24 小时）"}}

    def unknown(method, path, **kwargs):
        return 404, {}, {"detail": {"status": "unknown", "message": "策略任务不存在：run_id 无效或服务已重启"}}

    def legacy(method, path, **kwargs):
        return 404, {}, {"detail": "策略任务不存在或已过期"}

    with patch("app.routers.strategy.forward_re", expired):
        body = client.get("/api/strategy/joinquant/runs/r1").json()
    assert body["status"] == "expired"

    with patch("app.routers.strategy.forward_re", unknown):
        body = client.get("/api/strategy/joinquant/runs/r2").json()
    assert body["status"] == "unknown"

    with patch("app.routers.strategy.forward_re", legacy):
        body = client.get("/api/strategy/joinquant/runs/r3").json()
    assert body["status"] == "expired_or_unknown"
