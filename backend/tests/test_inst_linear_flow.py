# -*- coding: utf-8 -*-
"""线性流程 B：审批最后一关自动授权 + 模拟成交。

覆盖：
- Chairman/风控调用 approve-and-execute，一次完成授权与成交；
- 成交后议案 executed、订单 buy、持仓出现；
- 重复调用幂等；
- 非 Chairman/风控调用被拒绝；
- 审计查询返回操作人姓名/角色。
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


def _mk_member(conn, org_id: int, role: str, tag: str) -> tuple[dict, dict, str]:
    user = _mk_user(conn, f"inst_linear_{role}_{tag}")
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
            (f"linear-{tag}", f"线性流程测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, ref_price) "
            "VALUES (%s,%s,'线性流程测试公司','CN',100) RETURNING id",
            (org_id, f"LNR{tag[:4].upper()}.SH"),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_portfolio (org_id, code, name, base_currency, nav, cash) "
            "VALUES (%s,'MAIN','线性流程组合','CNY',10000000,10000000)",
            (org_id,),
        )
        users = []
        tokens: dict[str, str] = {}
        for role in ("manager", "partner", "chairman", "risk"):
            user, _membership, token = _mk_member(conn, org_id, role, tag)
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
        conn.execute(
            "DELETE FROM inst_fill WHERE order_id IN ("
            " SELECT o.id FROM inst_order o JOIN inst_portfolio p ON p.id=o.portfolio_id"
            " WHERE p.org_id=%s)",
            (org_id,),
        )
        conn.execute(
            "DELETE FROM inst_order WHERE portfolio_id IN"
            " (SELECT id FROM inst_portfolio WHERE org_id=%s)",
            (org_id,),
        )
        conn.execute(
            "DELETE FROM inst_position_snapshot WHERE portfolio_id IN"
            " (SELECT id FROM inst_portfolio WHERE org_id=%s)",
            (org_id,),
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


def test_approve_and_execute_full_linear_flow(fixture) -> None:
    tokens = fixture["tokens"]
    client = TestClient(app)

    case = _ok(
        client.post(
            "/api/inst/cases",
            json={"company_id": fixture["company_id"]},
            headers=_h(tokens["manager"]),
        )
    )
    case_id = int(case["id"])
    research = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/research",
            json={"mode": "valuation"},
            headers=_h(tokens["manager"]),
        )
    )
    version_id = int(research["versions"][0]["id"])
    version = research["versions"][0]
    assert version.get("content_hash")
    assert version.get("cutoff")
    assert research.get("evidence")
    assert all(ev.get("grade") in {"A", "B", "C", "D"} for ev in research["evidence"])
    assert all(ev.get("available_time") or ev.get("as_of") for ev in research["evidence"])
    _ok(
        client.post(
            f"/api/inst/research/{version_id}/review",
            json={"decision": "approve", "comment": "通过"},
            headers=_h(tokens["partner"]),
        )
    )
    debate = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/debate",
            json={"use_ai": False},
            headers=_h(tokens["manager"]),
        )
    )
    checks = _ok(
        client.get(f"/api/inst/debates/{int(debate['id'])}", headers=_h(tokens["manager"]))
    ).get("evidence_checks") or []
    assert checks
    assert all(item["status"] in {"verified", "partially_verified", "unverified", "contradicted"} for item in checks)
    assert all(item.get("claim_id") for item in checks)
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
                "investment_opinion": "E2E 投资意见：关键假设成立才持有",
            },
            headers=_h(tokens["manager"]),
        )
    )
    proposal_id = int(proposal["id"])
    with get_conn() as conn:
        snapshot = conn.execute(
            "SELECT snapshot FROM inst_proposal_version WHERE proposal_id=%s ORDER BY version_no DESC LIMIT 1",
            (proposal_id,),
        ).fetchone()["snapshot"]
        version_hash = conn.execute(
            "SELECT content_hash FROM inst_research_version WHERE id=%s", (version_id,)
        ).fetchone()["content_hash"]
    assert snapshot["research_content_hash"] == version_hash
    assert snapshot["evidence_hash"]
    assert snapshot["price_low"] == 100
    assert snapshot["price_high"] == 120
    assert snapshot["funding_source"] == "现金"
    assert snapshot["investment_opinion"].startswith("E2E 投资意见")
    assert snapshot["monitoring"] == ["季度财报后复核"]
    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/partner",
            json={"decision": "approve"},
            headers=_h(tokens["partner"]),
        )
    )
    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/chairman",
            json={"decision": "approve"},
            headers=_h(tokens["chairman"]),
        )
    )
    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/risk-check",
            json={},
            headers=_h(tokens["risk"]),
        )
    )

    # 经理不能触发自动成交。
    assert (
        client.post(
            f"/api/inst/proposals/{proposal_id}/approve-and-execute",
            json={"price": 100},
            headers=_h(tokens["manager"]),
        ).status_code
        == 403
    )

    out = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/approve-and-execute",
            json={"price": 100},
            headers=_h(tokens["chairman"]),
        )
    )
    assert out["proposal"]["status"] == "executed"
    assert out["execution"]["order"]["side"] == "buy"
    assert int(out["authorization_id"]) > 0
    with get_conn() as conn:
        auth_snapshot = conn.execute(
            "SELECT snapshot FROM inst_authorization WHERE id=%s", (int(out["authorization_id"]),)
        ).fetchone()["snapshot"]
    assert auth_snapshot["research_content_hash"] == version_hash
    assert auth_snapshot["evidence_hash"]
    assert auth_snapshot["proposal_hash"]

    portfolio = _ok(client.get("/api/inst/portfolio", headers=_h(tokens["manager"])))
    positions = [p for p in portfolio["positions"] if int(p["qty"]) > 0]
    assert positions, portfolio

    # 重复调用幂等，不重复成交。
    again = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/approve-and-execute",
            json={"price": 100},
            headers=_h(tokens["chairman"]),
        )
    )
    assert again["execution"].get("idempotent") is True
    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM inst_order o JOIN inst_portfolio p ON p.id=o.portfolio_id"
            " WHERE p.org_id=%s",
            (fixture["org_id"],),
        ).fetchone()["n"]
    assert int(count) == 1

    # 审计查询带操作人姓名/角色。
    audit = _ok(client.get("/api/inst/audit?limit=20", headers=_h(tokens["manager"])))
    executed_rows = [a for a in audit["items"] if a["action"] == "authorization.execute"]
    assert executed_rows
    assert executed_rows[0].get("actor_name")
    assert executed_rows[0].get("actor_role") == "chairman"
