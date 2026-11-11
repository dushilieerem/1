# -*- coding: utf-8 -*-
"""投委会审批顺序、多人审批、风控一票否决与附条件执行。

覆盖：
- 顺序固定：合伙人 → 风控 → Chairman，不能跳级；
- 同角色多人：各自留痕，任一风控否决即冻结；
- 提案人回避；
- 六项风控检查；
- 附条件随授权传递，执行前需确认条件。
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

RISK_CHECK_KEYS = {
    "concentration",
    "cash",
    "version",
    "validity_price",
    "trading_qualification",
    "duplicate_conflict",
}


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


def _mk_member(conn, org_id: int, role: str, tag: str, suffix: str) -> tuple[dict, str]:
    user = _mk_user(conn, f"inst_appr_{role}_{suffix}_{tag}")
    membership = conn.execute(
        "INSERT INTO inst_members (org_id, user_id, role) VALUES (%s,%s,%s) RETURNING *",
        (org_id, user["id"], role),
    ).fetchone()
    token = issue_inst_token(user, dict(membership))
    return user, token


@pytest.fixture(scope="module")
def fixture():
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"appr-{tag}", f"审批顺序测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, industry, ref_price) "
            "VALUES (%s,%s,'审批顺序测试公司','CN','测试行业',100) RETURNING id",
            (org_id, f"APR{tag[:4].upper()}.SH"),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_portfolio (org_id, code, name, base_currency, nav, cash) "
            "VALUES (%s,'MAIN','审批顺序组合','CNY',10000000,10000000)",
            (org_id,),
        )
        users: list[dict] = []
        tokens: dict[str, str] = {}
        members: dict[str, int] = {}
        for role, suffix in (
            ("manager", "m"),
            ("partner", "p1"),
            ("partner", "p2"),
            ("risk", "r1"),
            ("risk", "r2"),
            ("chairman", "c1"),
        ):
            user, token = _mk_member(conn, org_id, role, tag, suffix)
            users.append(user)
            tokens[suffix] = token
            members[suffix] = int(
                conn.execute(
                    "SELECT id FROM inst_members WHERE org_id=%s AND user_id=%s",
                    (org_id, user["id"]),
                ).fetchone()["id"]
            )
    yield {
        "org_id": org_id,
        "company_id": int(company["id"]),
        "tokens": tokens,
        "members": members,
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


def _new_proposal(client: TestClient, fixture, tokens) -> int:
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, industry, ref_price) "
            "VALUES (%s,%s,%s,'CN','测试行业',100) RETURNING id",
            (fixture["org_id"], f"APR{tag[:5].upper()}.SH", f"审批测试公司{tag}"),
        ).fetchone()
    case = _ok(
        client.post(
            "/api/inst/cases",
            json={"company_id": int(company["id"])},
            headers=_h(tokens["m"]),
        )
    )
    case_id = int(case["id"])
    research = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/research",
            json={"mode": "valuation"},
            headers=_h(tokens["m"]),
        )
    )
    version_id = int(research["versions"][0]["id"])
    _ok(
        client.post(
            f"/api/inst/research/{version_id}/lock",
            json={"allow_gaps": True, "comment": "审批顺序测试：显式带缺口锁定"},
            headers=_h(tokens["m"]),
        )
    )
    _ok(
        client.post(
            f"/api/inst/cases/{case_id}/debate",
            json={"use_ai": False},
            headers=_h(tokens["m"]),
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
            headers=_h(tokens["m"]),
        )
    )
    return int(proposal["id"])


def test_fixed_order_and_risk_veto(fixture) -> None:
    tokens = fixture["tokens"]
    client = TestClient(app)
    proposal_id = _new_proposal(client, fixture, tokens)

    # 跳级：合伙人与风控都没过，Chairman 不能批。
    assert (
        client.post(
            f"/api/inst/proposals/{proposal_id}/chairman",
            json={"decision": "approve"},
            headers=_h(tokens["c1"]),
        ).status_code
        == 403
    )
    # 合伙人都没批，风控不能先跑。
    assert (
        client.post(
            f"/api/inst/proposals/{proposal_id}/risk-check",
            json={},
            headers=_h(tokens["r1"]),
        ).status_code
        == 403
    )

    first = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/partner",
            json={"decision": "approve"},
            headers=_h(tokens["p1"]),
        )
    )
    # 同角色多人：全部合伙人给出意见后才进入风控。
    assert first["status"] == "partner_review"
    pending = _ok(client.get("/api/inst/proposals", headers=_h(tokens["p2"])))
    assert any(int(item["id"]) == proposal_id for item in pending["items"])

    second = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/partner",
            json={"decision": "approve"},
            headers=_h(tokens["p2"]),
        )
    )
    assert second["status"] == "risk_precheck"

    passed = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/risk-check",
            json={"decision": "pass"},
            headers=_h(tokens["r1"]),
        )
    )
    assert passed["status"] == "risk_precheck"
    assert {c["key"] for c in passed["risk_checks"]} == RISK_CHECK_KEYS
    assert all(c["status"] in {"pass", "warn", "block"} for c in passed["risk_checks"])

    # 另一名风控否决：一票否决终局，Chairman 不能救。
    veto = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/risk-check",
            json={"decision": "veto", "comment": "红线不可接受"},
            headers=_h(tokens["r2"]),
        )
    )
    assert veto["status"] == "frozen"
    assert (
        client.post(
            f"/api/inst/proposals/{proposal_id}/chairman",
            json={"decision": "approve"},
            headers=_h(tokens["c1"]),
        ).status_code
        == 403
    )
    with get_conn() as conn:
        risk_rows = conn.execute(
            "SELECT COUNT(*) AS n FROM inst_approval a"
            " JOIN inst_proposal_version v ON v.id=a.proposal_version_id"
            " WHERE v.proposal_id=%s AND a.step='risk_precheck'",
            (proposal_id,),
        ).fetchone()["n"]
    assert int(risk_rows) == 2


def test_proposer_cannot_approve_own_proposal(fixture) -> None:
    tokens = fixture["tokens"]
    client = TestClient(app)
    proposal_id = _new_proposal(client, fixture, tokens)
    with get_conn() as conn:
        conn.execute(
            "UPDATE inst_proposal SET created_by=%s WHERE id=%s",
            (fixture["members"]["p1"], proposal_id),
        )
    assert (
        client.post(
            f"/api/inst/proposals/{proposal_id}/partner",
            json={"decision": "approve"},
            headers=_h(tokens["p1"]),
        ).status_code
        == 403
    )


def test_conditions_flow_and_execution_gate(fixture) -> None:
    tokens = fixture["tokens"]
    client = TestClient(app)
    proposal_id = _new_proposal(client, fixture, tokens)

    partner = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/partner",
            json={
                "decision": "conditional",
                "comment": "补齐同业对标后可上会",
                "conditions": ["补充同业对标数据"],
            },
            headers=_h(tokens["p1"]),
        )
    )
    assert partner["status"] == "partner_review"
    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/partner",
            json={"decision": "approve"},
            headers=_h(tokens["p2"]),
        )
    )
    risk = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/risk-check",
            json={
                "decision": "conditional",
                "comment": "现价回区间后放行",
                "conditions": ["现价回到 100-120 才可执行"],
            },
            headers=_h(tokens["r1"]),
        )
    )
    assert risk["status"] == "risk_precheck"
    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/risk-check",
            json={"decision": "pass"},
            headers=_h(tokens["r2"]),
        )
    )
    chairman = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/chairman",
            json={
                "decision": "conditional",
                "comment": "批准，建仓后补足现金",
                "conditions": ["建仓后 5 日内补足现金"],
            },
            headers=_h(tokens["c1"]),
        )
    )
    assert chairman["status"] == "authorized"

    authorized = _ok(
        client.post(f"/api/inst/proposals/{proposal_id}/authorize", headers=_h(tokens["c1"]))
    )
    auth = authorized["authorizations"][0]
    assert len(auth["snapshot"]["approval_conditions"]) == 3
    assert auth["snapshot"]["monitoring"] == ["季度财报后复核"]

    # 有附加条件时，执行人必须确认条件已满足。
    assert (
        client.post(
            f"/api/inst/authorizations/{int(auth['id'])}/execute",
            json={"price": 110},
            headers=_h(tokens["m"]),
        ).status_code
        == 403
    )
    executed = _ok(
        client.post(
            f"/api/inst/authorizations/{int(auth['id'])}/execute",
            json={"price": 110, "conditions_met": True},
            headers=_h(tokens["m"]),
        )
    )
    assert executed["order"]["side"] == "buy"
    assert executed["order"]["status"] == "filled"
