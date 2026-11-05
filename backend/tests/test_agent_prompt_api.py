# -*- coding: utf-8 -*-
"""个人中心 Agent 管理 API：列表、权限、提示词版本与重置。"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")
os.environ.setdefault("RE_CATALOG_SYNC_ENABLED", "0")
os.environ.setdefault("SVQUANT_PANEL_DAILY_ENABLED", "0")
os.environ.setdefault("SVQUANT_PAPER_TRADING_ENABLED", "0")
os.environ.setdefault("NEWS_INGEST_INTERVAL_SEC", "0")
os.environ.setdefault("RE_CATALOG_WARM_ENABLED", "0")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from ai.runtime import agent_store  # noqa: E402
from services.auth.auth_store import ensure_schema, issue_token  # noqa: E402
from services.core.db import get_conn  # noqa: E402

ensure_schema()
agent_store.ensure_ai_agent_schema()


def _user(role: str, tag: str) -> tuple[dict, str]:
    username = f"agent_api_{role}_{tag}"
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s,'!',%s) "
            "RETURNING id, username, role, token_version",
            (username, role),
        ).fetchone()
    user = dict(row)
    return user, issue_token(user)


def test_agent_catalog_permissions_and_prompt_version() -> None:
    tag = uuid.uuid4().hex[:8]
    admin, admin_token = _user("admin", tag)
    normal, normal_token = _user("user", tag)
    client = TestClient(app)
    ah = {"Authorization": f"Bearer {admin_token}"}
    nh = {"Authorization": f"Bearer {normal_token}"}

    listing = client.get("/api/agent/agents", headers=nh)
    assert listing.status_code == 200, listing.text
    data = listing.json()
    assert data["can_edit"] is False
    assert data["count"] >= 14
    institution = next(item for item in data["items"] if item["task_id"] == "inst.research_memo")
    assert institution["editable"] is True
    assert institution["prompt"] is None

    admin_listing = client.get("/api/agent/agents", headers=ah).json()
    assert admin_listing["can_edit"] is True
    admin_memo = next(item for item in admin_listing["items"] if item["task_id"] == "inst.research_memo")
    assert admin_memo["prompt"]
    assert admin_memo["default_prompt"]

    denied = client.put(
        "/api/agent/agents/inst.research_memo/prompt",
        json={"prompt": "普通用户不能改"},
        headers=nh,
    )
    assert denied.status_code == 403

    saved = client.put(
        "/api/agent/agents/inst.research_memo/prompt",
        json={"prompt": "管理员自定义提示词：50 字结论", "note": "测试"},
        headers=ah,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] >= 1
    prompt, version = agent_store.get_effective_prompt("inst.research_memo", "默认")
    assert prompt.startswith("管理员自定义")
    assert version != "0"

    history = client.get("/api/agent/agents/inst.research_memo/prompt/history", headers=ah)
    assert history.status_code == 200
    assert history.json()["items"][0]["action"] == "save"

    reset = client.post("/api/agent/agents/inst.research_memo/prompt/reset", headers=ah)
    assert reset.status_code == 200
    prompt, version = agent_store.get_effective_prompt("inst.research_memo", "默认")
    assert prompt == "默认"
    assert version == "0"

    # 非机构 Agent 只读。
    readonly = client.put(
        "/api/agent/agents/invest.daily/prompt",
        json={"prompt": "不应允许"},
        headers=ah,
    )
    assert readonly.status_code == 400

    # 清理：避免历史版本影响后续测试。
    with get_conn() as conn:
        conn.execute("DELETE FROM ai_agent_prompt WHERE task_id='inst.research_memo'")
        conn.execute("DELETE FROM users WHERE id IN (%s,%s)", (admin["id"], normal["id"]))
