# -*- coding: utf-8 -*-
"""机构端 Agent 管理：目录、经理权限、提示词版本与重置。"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

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
from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.institution.inst_schema import ensure_inst_business_schema  # noqa: E402
from services.institution.inst_store import ensure_inst_schema, issue_inst_token  # noqa: E402

ensure_schema()
ensure_inst_schema()
ensure_inst_business_schema()
agent_store.ensure_ai_agent_schema()


def _mk_member(conn, org_id: int, role: str, tag: str) -> tuple[dict, dict, str]:
    user = conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (%s,'!') RETURNING id, username, role, status",
        (f"inst_agent_{role}_{tag}",),
    ).fetchone()
    user_dict = dict(user)
    membership = conn.execute(
        "INSERT INTO inst_members (org_id, user_id, role) VALUES (%s,%s,%s) RETURNING *",
        (org_id, int(user["id"]), role),
    ).fetchone()
    member = dict(membership)
    return user_dict, member, issue_inst_token(user_dict, member)


@pytest.fixture(scope="module")
def fixture():
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"agents-{tag}", f"Agent 管理测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        manager, _, manager_token = _mk_member(conn, org_id, "manager", tag)
        partner, _, partner_token = _mk_member(conn, org_id, "partner", tag)
    return {
        "org_id": org_id,
        "manager_id": int(manager["id"]),
        "partner_id": int(partner["id"]),
        "manager_token": manager_token,
        "partner_token": partner_token,
    }


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_institution_agent_catalog_and_prompt_versions(fixture) -> None:
    client = TestClient(app)
    manager_headers = _h(fixture["manager_token"])
    partner_headers = _h(fixture["partner_token"])

    listing = client.get("/api/inst/agents", headers=manager_headers)
    assert listing.status_code == 200, listing.text
    data = listing.json()
    assert data["can_edit"] is True
    assert data["count"] >= 14
    memo = next(item for item in data["items"] if item["task_id"] == "inst.research_memo")
    assert memo["editable"] is True
    assert memo["prompt"]

    read_only = client.get("/api/inst/agents", headers=partner_headers)
    assert read_only.status_code == 200
    partner_data = read_only.json()
    assert partner_data["can_edit"] is False
    partner_memo = next(item for item in partner_data["items"] if item["task_id"] == "inst.research_memo")
    assert partner_memo["prompt"] is None

    denied = client.put(
        "/api/inst/agents/inst.research_memo/prompt",
        json={"prompt": "合伙人不能改"},
        headers=partner_headers,
    )
    assert denied.status_code == 403

    saved = client.put(
        "/api/inst/agents/inst.research_memo/prompt",
        json={"prompt": "经理自定义提示词：50 字结论", "note": "测试"},
        headers=manager_headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] >= 1
    prompt, version = agent_store.get_effective_prompt("inst.research_memo", "默认")
    assert prompt.startswith("经理自定义")
    assert version != "0"

    history = client.get("/api/inst/agents/inst.research_memo/prompt/history", headers=manager_headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["action"] == "save"

    reset = client.post("/api/inst/agents/inst.research_memo/prompt/reset", headers=manager_headers)
    assert reset.status_code == 200
    prompt, version = agent_store.get_effective_prompt("inst.research_memo", "默认")
    assert prompt == "默认"
    assert version == "0"

    readonly = client.put(
        "/api/inst/agents/invest.daily/prompt",
        json={"prompt": "不应允许"},
        headers=manager_headers,
    )
    assert readonly.status_code == 400

    with get_conn() as conn:
        conn.execute("DELETE FROM ai_agent_prompt WHERE task_id='inst.research_memo'")
