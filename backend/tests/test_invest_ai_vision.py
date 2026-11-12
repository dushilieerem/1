# -*- coding: utf-8 -*-
"""H5 截图识图：多模态消息、字数与错误边界。"""
from __future__ import annotations

import base64

import pytest
from fastapi import HTTPException

from app.routers import invest_ai
from services.invest import agent_tools


class FakeConn:
    pass


PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
).decode()


def test_vision_sends_image_url_and_returns_text(monkeypatch):
    captured = {}

    def fake_run_task(task_id, **kwargs):
        captured["task_id"] = task_id
        captured["messages"] = kwargs["messages"]
        return {"content": "分析 宁德时代(300750)", "data": {"text": "分析 宁德时代(300750)"}, "model": "vision-test"}

    monkeypatch.setattr("ai.router.available_task", lambda task_id: True)
    monkeypatch.setattr("ai.router.run_task", fake_run_task)
    monkeypatch.setattr(
        agent_tools,
        "correct_entities",
        lambda conn, text: {"text": "分析 宁德时代(300750)", "corrections": []},
    )
    out = invest_ai.vision({"image_base64": PNG, "mime": "image/png"}, {"id": 1}, FakeConn())
    assert out["ok"] is True and "宁德时代" in out["text"]
    assert captured["task_id"] == "invest.vision"
    user_content = captured["messages"][1]["content"]
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_vision_rejects_bad_mime():
    with pytest.raises(HTTPException) as exc:
        invest_ai.vision({"image_base64": PNG, "mime": "text/plain"}, {"id": 1}, FakeConn())
    assert exc.value.status_code == 400


def test_vision_requires_configured_task(monkeypatch):
    monkeypatch.setattr("ai.router.available_task", lambda task_id: False)
    with pytest.raises(HTTPException) as exc:
        invest_ai.vision({"image_base64": PNG, "mime": "image/png"}, {"id": 1}, FakeConn())
    assert exc.value.status_code == 503
