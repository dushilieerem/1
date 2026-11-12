# -*- coding: utf-8 -*-
"""审批台四套角色页面：列表过滤、详情权限与可见字段边界。"""
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
from services.institution.inst_schema import ensure_inst_business_schema  # noqa: E402
from services.institution.inst_store import ensure_inst_schema, issue_inst_token  # noqa: E402

ensure_schema()
ensure_inst_schema()
ensure_inst_business_schema()


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


def _mk_member(conn, org_id: int, role: str, tag: str, suffix: str) -> tuple[dict, str, int]:
    user = _mk_user(conn, f"inst_roles_{role}_{suffix}_{tag}")
    membership = conn.execute(
        "INSERT INTO inst_members (org_id, user_id, role) VALUES (%s,%s,%s) RETURNING *",
        (org_id, user["id"], role),
    ).fetchone()
    token = issue_inst_token(user, dict(membership))
    return user, token, int(membership["id"])


@pytest.fixture(scope="module")
def fixture():
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"roles-{tag}", f"审批角色测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, industry, ref_price) "
            "VALUES (%s,%s,'审批角色测试公司','CN','测试行业',100) RETURNING id",
            (org_id, f"ROL{tag[:4].upper()}.SH"),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_portfolio (org_id, code, name, base_currency, nav, cash) "
            "VALUES (%s,'MAIN','角色测试组合','CNY',10000000,10000000)",
            (org_id,),
        )
        users: list[dict] = []
        tokens: dict[str, str] = {}
        members: dict[str, int] = {}
        for role, suffix in (
            ("manager", "m1"),
            ("manager", "m2"),
            ("partner", "p1"),
            ("partner", "p2"),
            ("risk", "r1"),
            ("chairman", "c1"),
        ):
            user, token, member_id = _mk_member(conn, org_id, role, tag, suffix)
            users.append(user)
            tokens[suffix] = token
            members[suffix] = member_id
    yield {
        "org_id": org_id,
        "company_id": int(company["id"]),
        "tokens": tokens,
        "members": members,
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


def _new_proposal(client: TestClient, fixture, manager_token: str, partner_token: str) -> int:
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, industry, ref_price) "
            "VALUES (%s,%s,%s,'CN','测试行业',100) RETURNING id",
            (fixture["org_id"], f"ROL{tag[:5].upper()}.SH", f"角色测试公司{tag}"),
        ).fetchone()
    case = _ok(
        client.post(
            "/api/inst/cases",
            json={"company_id": int(company["id"])},
            headers=_h(manager_token),
        )
    )
    case_id = int(case["id"])
    research = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/research",
            json={"mode": "valuation"},
            headers=_h(manager_token),
        )
    )
    version_id = int(research["versions"][0]["id"])
    _ok(
        client.post(
            f"/api/inst/research/{version_id}/lock",
            json={"allow_gaps": True, "comment": "角色测试：显式带缺口锁定"},
            headers=_h(manager_token),
        )
    )
    _ok(
        client.post(
            f"/api/inst/cases/{case_id}/debate",
            json={"use_ai": False},
            headers=_h(manager_token),
        )
    )
    proposal = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/proposals",
            json={
                "direction": "buy",
                "target_weight": 0.02,
                "price_low": 100,
                "price_high": 120,
                "funding_source": "现金",
                "valid_until": "2099-12-31",
                "monitoring": ["季度财报后复核"],
                "investment_opinion": "关键假设成立才持有",
            },
            headers=_h(manager_token),
        )
    )
    return int(proposal["id"])


def test_role_lists_and_field_boundaries(fixture) -> None:
    tokens = fixture["tokens"]
    client = TestClient(app)
    proposal_a = _new_proposal(client, fixture, tokens["m1"], tokens["p1"])
    proposal_b = _new_proposal(client, fixture, tokens["m2"], tokens["p1"])

    # 投资经理：只看自己的议案；详情没有审批明细、风控逐项与 Agent 数据。
    m1_list = _ok(client.get("/api/inst/proposals", headers=_h(tokens["m1"])))
    assert {int(item["id"]) for item in m1_list["items"]} == {proposal_a}
    m2_list = _ok(client.get("/api/inst/proposals", headers=_h(tokens["m2"])))
    assert {int(item["id"]) for item in m2_list["items"]} == {proposal_b}

    m1_detail = _ok(client.get(f"/api/inst/proposals/{proposal_a}", headers=_h(tokens["m1"])))
    assert m1_detail["progress"]["partner"]["reviewed"] == 0
    assert m1_detail["progress"]["partner"]["total"] == 2
    assert "approvals" not in m1_detail
    assert "risk_checks" not in m1_detail
    assert "research_debate" not in m1_detail
    assert m1_detail["current_version"]["snapshot"]["investment_opinion"]
    assert (
        client.get(f"/api/inst/proposals/{proposal_b}", headers=_h(tokens["m1"])).status_code
        == 403
    )

    # 合伙人：待审只含轮到本关且本人未给意见的议案；详情有研究与辩论，没有风控逐项。
    p1_pending = _ok(client.get("/api/inst/proposals", headers=_h(tokens["p1"])))
    assert {int(item["id"]) for item in p1_pending["items"]} == {proposal_a, proposal_b}
    p1_detail = _ok(client.get(f"/api/inst/proposals/{proposal_a}", headers=_h(tokens["p1"])))
    assert p1_detail["research_debate"]["six_dim"] is not None
    assert "risk_checks" not in p1_detail
    assert "approval_chain" not in p1_detail

    # 风控/Chairman 在合伙人未通过前看不到该议案。
    assert client.get(f"/api/inst/proposals/{proposal_a}", headers=_h(tokens["r1"])).status_code == 403
    assert client.get(f"/api/inst/proposals/{proposal_a}", headers=_h(tokens["c1"])).status_code == 403

    # 两位合伙人都给出意见后才进入风控；已审列表保留记录。
    first = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_a}/partner",
            json={"decision": "approve"},
            headers=_h(tokens["p1"]),
        )
    )
    assert first["status"] == "partner_review"
    p2_pending = _ok(client.get("/api/inst/proposals", headers=_h(tokens["p2"])))
    assert proposal_a in {int(item["id"]) for item in p2_pending["items"]}
    p1_pending_after = _ok(client.get("/api/inst/proposals", headers=_h(tokens["p1"])))
    assert proposal_a not in {int(item["id"]) for item in p1_pending_after["items"]}
    p1_reviewed = _ok(
        client.get("/api/inst/proposals?scope=reviewed", headers=_h(tokens["p1"]))
    )
    assert proposal_a in {int(item["id"]) for item in p1_reviewed["items"]}

    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_a}/partner",
            json={"decision": "approve"},
            headers=_h(tokens["p2"]),
        )
    )
    p1_after = _ok(client.get(f"/api/inst/proposals/{proposal_a}", headers=_h(tokens["p1"])))
    assert p1_after["my_decision"]["decision"] == "approve"
    assert p1_after["progress"]["partner"]["reviewed"] == 2

    # 风控：只拿到合伙人已通过的案件；详情有六项核查与合伙人结论，没有研究与辩论全文。
    r_pending = _ok(client.get("/api/inst/proposals", headers=_h(tokens["r1"])))
    assert proposal_a in {int(item["id"]) for item in r_pending["items"]}
    r_detail = _ok(client.get(f"/api/inst/proposals/{proposal_a}", headers=_h(tokens["r1"])))
    assert len(r_detail["risk_checks"]) == 6
    assert r_detail["partner_stage"]["status"] == "approved"
    assert "research_debate" not in r_detail
    assert "approval_chain" not in r_detail

    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_a}/risk-check",
            json={"decision": "pass"},
            headers=_h(tokens["r1"]),
        )
    )

    # Chairman：前两关都通过后才可见；详情有完整审批链、风控结论与研究裁决，没有六项逐条明细。
    c_pending = _ok(client.get("/api/inst/proposals", headers=_h(tokens["c1"])))
    assert proposal_a in {int(item["id"]) for item in c_pending["items"]}
    c_detail = _ok(client.get(f"/api/inst/proposals/{proposal_a}", headers=_h(tokens["c1"])))
    assert c_detail["risk_stage"]["status"] == "passed"
    assert c_detail["approval_chain"]
    assert c_detail["research_debate"]
    assert "risk_checks" not in c_detail

    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_a}/chairman",
            json={"decision": "approve"},
            headers=_h(tokens["c1"]),
        )
    )
    m1_final = _ok(client.get(f"/api/inst/proposals/{proposal_a}", headers=_h(tokens["m1"])))
    assert m1_final["progress"]["chairman"]["status"] == "approved"
    assert m1_final["authorization"] is None or m1_final["authorization"]["status"] == "qualified"
