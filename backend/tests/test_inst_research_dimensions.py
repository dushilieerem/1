# -*- coding: utf-8 -*-
"""研究页单维视图、逐维审核、单维追问与研究一页纸。

覆盖 2026-11-03 前端需求：
- 单维重新分析合并进最近一版，保留其余五维；
- 逐维审核写入 dim_reviews 与审计，整体审核仍可继续；
- 单维追问只带该维上下文，AI 未配置时明确失败；
- AI 一页纸返回 metrics；AI 不可用时回退规则摘要。
"""
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
from services.auth.auth_store import ensure_schema, issue_token  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.institution import inst_service as svc  # noqa: E402
from services.institution.inst_schema import ensure_inst_business_schema  # noqa: E402
from services.institution.inst_store import ensure_inst_schema, issue_inst_token  # noqa: E402

ensure_schema()
ensure_inst_schema()
ensure_inst_business_schema()

DIM_KEYS = ["industry", "business_model", "moat", "financial", "governance", "valuation"]


def _mk_user(conn, username: str) -> dict:
    row = conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (%s,'!') RETURNING id, username, role, status",
        (username,),
    ).fetchone()
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "role": str(row["role"]),
        "status": str(row["status"]),
    }


def _mk_member(conn, org_id: int, role: str, tag: str) -> tuple[dict, dict, str]:
    user = _mk_user(conn, f"inst_dim_{role}_{tag}")
    membership = conn.execute(
        "INSERT INTO inst_members (org_id, user_id, role) VALUES (%s,%s,%s) RETURNING *",
        (org_id, user["id"], role),
    ).fetchone()
    return user, dict(membership), issue_inst_token(user, dict(membership))


@pytest.fixture(scope="module")
def fixture():
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"dim-{tag}", f"单维测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, ref_price) "
            "VALUES (%s,%s,'单维测试公司','CN',100) RETURNING id",
            (org_id, f"TEST{tag[:4].upper()}.SH"),
        ).fetchone()
        users = []
        tokens: dict[str, str] = {}
        for role in ("manager", "partner"):
            user, membership, token = _mk_member(conn, org_id, role, tag)
            users.append(user)
            tokens[role] = token
    yield {
        "org_id": org_id,
        "company_id": int(company["id"]),
        "tokens": tokens,
        "users": users,
    }
    with get_conn() as conn:
        conn.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='inst_audit_event_worm')"
            " THEN ALTER TABLE inst_audit_event DISABLE TRIGGER inst_audit_event_worm; END IF; END $$"
        )
        conn.execute("DELETE FROM inst_orgs WHERE id=%s", (org_id,))
        conn.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='inst_audit_event_worm')"
            " THEN ALTER TABLE inst_audit_event ENABLE TRIGGER inst_audit_event_worm; END IF; END $$"
        )
        for user in users:
            conn.execute("DELETE FROM users WHERE id=%s", (user["id"],))


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _ok(resp, code: int = 200) -> dict:
    assert resp.status_code == code, f"{resp.status_code} {resp.text[:400]}"
    return resp.json()


def _case_with_research(client: TestClient, fixture: dict) -> tuple[int, dict]:
    case = _ok(
        client.post(
            "/api/inst/cases",
            json={"company_id": fixture["company_id"]},
            headers=_h(fixture["tokens"]["manager"]),
        )
    )
    case_id = int(case["id"])
    data = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/research",
            json={"mode": "full"},
            headers=_h(fixture["tokens"]["manager"]),
        )
    )
    return case_id, data


def test_return_targets_reruns_selected_and_keeps_others(fixture) -> None:
    client = TestClient(app)
    case_id, data = _case_with_research(client, fixture)
    first = data["versions"][0]
    assert first.get("industry_analysis")
    out = _ok(
        client.post(
            f"/api/inst/research/{int(first['id'])}/review",
            json={
                "decision": "return",
                "comment": "行业和财务需要重跑",
                "targets": ["industry", "financial"],
            },
            headers=_h(fixture["tokens"]["partner"]),
        )
    )
    latest = out["versions"][0]
    assert int(latest["version_no"]) == int(first["version_no"]) + 1
    assert latest["status"] == "pending_review"
    assert [d["key"] for d in latest["six_dim"]] == DIM_KEYS
    assert latest.get("industry_analysis")
    assert latest.get("industry_analysis", {}).get("summary")

def test_single_dimension_regeneration_keeps_six_dims(fixture) -> None:
    client = TestClient(app)
    case_id, data = _case_with_research(client, fixture)
    first = data["versions"][0]
    assert [d["key"] for d in first["six_dim"]] == DIM_KEYS
    assert first["dim_reviews"] == {}

    merged = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/research",
            json={"mode": "valuation"},
            headers=_h(fixture["tokens"]["manager"]),
        )
    )
    latest = merged["versions"][0]
    assert int(latest["version_no"]) == int(first["version_no"]) + 1
    assert [d["key"] for d in latest["six_dim"]] == DIM_KEYS
    assert latest["dim_reviews"] == {}
    # 旧版本仍完整保留，用于追溯。
    old = next(v for v in merged["versions"] if int(v["id"]) == int(first["id"]))
    assert len(old["six_dim"]) == 6

    with get_conn() as conn:
        audit = conn.execute(
            "SELECT after FROM inst_audit_event WHERE org_id=%s AND action='research.generate'"
            " AND object_id=%s",
            (fixture["org_id"], int(latest["id"])),
        ).fetchone()
    assert audit and audit["after"]["mode"] == "valuation"
    assert audit["after"]["merged_from_version_no"] == int(first["version_no"])


def test_per_dimension_review_then_global_approve(fixture) -> None:
    client = TestClient(app)
    _, data = _case_with_research(client, fixture)
    version = data["versions"][0]
    version_id = int(version["id"])

    for i, key in enumerate(DIM_KEYS):
        out = _ok(
            client.post(
                f"/api/inst/research/{version_id}/dimensions/{key}/review",
                json={"decision": "approve", "comment": f"第 {i + 1} 维通过"},
                headers=_h(fixture["tokens"]["manager"]),
            )
        )
        reviews = out["versions"][0]["dim_reviews"]
        assert reviews[key]["decision"] == "approve"
        assert reviews[key]["comment"] == f"第 {i + 1} 维通过"

    latest = _ok(client.get(f"/api/inst/cases/{data['id']}", headers=_h(fixture["tokens"]["manager"])))
    reviews = latest["versions"][0]["dim_reviews"]
    assert set(reviews) == set(DIM_KEYS)

    # 整体审核仍可继续，未破坏既有链路。
    approved = _ok(
        client.post(
            f"/api/inst/research/{version_id}/review",
            json={"decision": "approve", "comment": "逐维通过后整体通过"},
            headers=_h(fixture["tokens"]["manager"]),
        )
    )
    assert approved["versions"][0]["status"] == "approved"

    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM inst_audit_event WHERE org_id=%s"
            " AND action='research.review.dimension.approve'",
            (fixture["org_id"],),
        ).fetchone()["n"]
    assert int(count) == 6


def test_dimension_chat_uses_dimension_context_and_audits(fixture, monkeypatch) -> None:
    client = TestClient(app)
    case_id, _ = _case_with_research(client, fixture)
    seen: dict = {}

    def fake_task(task_id, payload, system):
        seen["task_id"] = task_id
        seen["payload"] = payload
        return {"answer": "护城河的关键反证是毛利率不可持续。", "engine": "agent"}

    monkeypatch.setattr(svc, "_ai_task", fake_task)
    out = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/dimensions/moat/chat",
            json={
                "question": "护城河的关键反证是什么？",
                "history": [
                    {"role": "user", "content": "先看护城河"},
                    {"role": "assistant", "content": "已看护城河"},
                ],
            },
            headers=_h(fixture["tokens"]["manager"]),
        )
    )
    assert out["answer"] == "护城河的关键反证是毛利率不可持续。"
    assert seen["task_id"] == "inst.dim.chat"
    assert seen["payload"]["dimension"]["key"] == "moat"
    assert seen["payload"]["question"] == "护城河的关键反证是什么？"
    assert len(seen["payload"]["history"]) == 2

    assert (
        client.post(
            f"/api/inst/cases/{case_id}/dimensions/moat/chat",
            json={"question": "   "},
            headers=_h(fixture["tokens"]["manager"]),
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/inst/cases/{case_id}/dimensions/nope/chat",
            json={"question": "?"},
            headers=_h(fixture["tokens"]["manager"]),
        ).status_code
        == 400
    )

    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM inst_audit_event WHERE org_id=%s"
            " AND action='research.dimension.chat'",
            (fixture["org_id"],),
        ).fetchone()["n"]
    assert int(count) == 1


def test_research_memo_has_metrics_and_rule_fallback(fixture, monkeypatch) -> None:
    client = TestClient(app)
    case_id, _ = _case_with_research(client, fixture)

    monkeypatch.setattr(
        svc,
        "_ai_task",
        lambda task_id, payload, system: {
            "summary": "AI 摘要",
            "risks": ["风险一"],
            "open_questions": ["核验一"],
        },
    )
    memo = _ok(
        client.post(f"/api/inst/cases/{case_id}/ai/memo", headers=_h(fixture["tokens"]["manager"]))
    )["memo"]
    assert memo["summary"] == "AI 摘要"
    assert isinstance(memo["metrics"], list)
    assert memo["engine"] == "agent"

    def unavailable(task_id, payload, system):
        raise svc.AiUnavailable("AI 未配置")

    monkeypatch.setattr(svc, "_ai_task", unavailable)
    fallback = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/ai/memo",
            json={"refresh": True},
            headers=_h(fixture["tokens"]["manager"]),
        )
    )["memo"]
    assert fallback["engine"] == "rule"
    assert fallback["summary"]
    assert fallback["decision"] == "watch"
    assert isinstance(fallback["metrics"], list)


def test_ideas_push_contract(fixture) -> None:
    """量化推送：返回策略元信息与只含正动量、估值过滤后的条目。"""
    out = svc.ideas_push(fixture["org_id"], limit=5)
    assert out["strategy"]["key"] == "momentum_valuation"
    assert isinstance(out["items"], list)
    assert out["as_of"] is None or isinstance(out["as_of"], str)
    for item in out["items"]:
        assert item["momentum"] > 0
        assert 2 <= item["momentum_window"] <= 20
        if item["pe_ttm"] is not None:
            assert 0 < float(item["pe_ttm"]) <= 100
        if item["pb_mrq"] is not None:
            assert float(item["pb_mrq"]) > 0
