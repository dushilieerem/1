# -*- coding: utf-8 -*-
"""C6：机构端业务全链路与权限穿透（TestClient + 临时机构）。

覆盖：建案 → 研究 → 审核 → 辩论 → 议案 → 合伙人 → Chairman → 风控 → 授权 → 执行
→ 论点台账 → 退出/复盘；以及个人令牌越权、角色越权、风控阻断后 Chairman 不能批准。
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")
# 测试不启动后台调度，避免写 factor/index.yaml、模拟盘结算等仓库副作用
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
    user = _mk_user(conn, f"inst_{role}_{tag}")
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
            (f"e2e-{tag}", f"E2E 机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, ref_price) "
            "VALUES (%s,'600519.SH','贵州茅台','CN',100) RETURNING id",
            (org_id,),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_portfolio (org_id, code, name, base_currency, nav, cash) "
            "VALUES (%s,'MAIN','E2E 组合','CNY',10000000,10000000)",
            (org_id,),
        )
        users = []
        tokens: dict[str, str] = {}
        members: dict[str, int] = {}
        for role in ("manager", "partner", "chairman", "risk", "execution", "monitoring"):
            user, membership, token = _mk_member(conn, org_id, role, tag)
            users.append(user)
            tokens[role] = token
            members[role] = int(membership["id"])
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
        # 订单/成交/持仓快照对 portfolio 的 FK 不带级联，先按组合清理。
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
    assert resp.status_code == code, f"{resp.status_code} {resp.text[:300]}"
    return resp.json()


def test_full_chain_and_permission_penetration(fixture) -> None:
    tokens = fixture["tokens"]
    manager, partner, chairman, risk, execution = (
        tokens["manager"],
        tokens["partner"],
        tokens["chairman"],
        tokens["risk"],
        tokens["execution"],
    )
    # 不进 lifespan：避免启动调度/迁移写仓库文件；schema 已在上方显式确保。
    client = TestClient(app)
    personal = issue_token(fixture["users"][0])
    assert client.get("/api/inst/overview", headers=_h(personal)).status_code == 401
    # chairman 无机会发现（ideas=none）工作区
    assert client.get("/api/inst/companies", headers=_h(chairman)).status_code == 403

    case = _ok(
        client.post(
            "/api/inst/cases",
            json={"company_id": fixture["company_id"]},
            headers=_h(manager),
        )
    )
    case_id = int(case["id"])

    research = _ok(
        client.post(f"/api/inst/cases/{case_id}/research", json={"mode": "full"}, headers=_h(manager))
    )
    version_id = int(research["versions"][0]["id"])
    _ok(
        client.post(
            f"/api/inst/research/{version_id}/review",
            json={"decision": "approve", "comment": "通过"},
            headers=_h(partner),
        )
    )
    _ok(
        client.post(
            f"/api/inst/cases/{case_id}/debate", json={"use_ai": False}, headers=_h(manager)
        )
    )

    proposal = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/proposals",
            json={"direction": "buy", "target_weight": 0.05},
            headers=_h(manager),
        )
    )
    proposal_id = int(proposal["id"])

    # 提案人角色 manager 不能做 Chairman 审批
    assert (
        client.post(
            f"/api/inst/proposals/{proposal_id}/chairman",
            json={"decision": "approve"},
            headers=_h(manager),
        ).status_code
        == 403
    )

    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/partner",
            json={"decision": "approve", "updates": {"target_weight": 0.05}},
            headers=_h(partner),
        )
    )
    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/chairman",
            json={"decision": "approve"},
            headers=_h(chairman),
        )
    )
    precheck = _ok(
        client.get(
            f"/api/inst/proposals/{proposal_id}/ai/chairman-precheck", headers=_h(chairman)
        )
    )
    assert precheck["binding"] is False
    simulate = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/ai/chairman-simulate", headers=_h(chairman)
        )
    )
    assert simulate["simulated_decision"] in {"approve", "conditional", "handover"}

    risk_out = _ok(
        client.post(f"/api/inst/proposals/{proposal_id}/risk-check", json={}, headers=_h(risk))
    )
    assert risk_out["status"] == "risk_precheck"

    authorized = _ok(
        client.post(f"/api/inst/proposals/{proposal_id}/authorize", headers=_h(chairman))
    )
    auth_id = int(authorized["authorizations"][0]["id"])
    precheck = _ok(
        client.get(f"/api/inst/authorizations/{auth_id}/precheck", headers=_h(execution))
    )
    assert precheck["checks"]
    if precheck.get("price"):
        # CI 的空行情库没有收盘价，此时只验证结构，不要求通过
        assert precheck["ok"] is True, precheck
    executed = _ok(
        client.post(
            f"/api/inst/authorizations/{auth_id}/execute",
            json={"price": 100},
            headers=_h(execution),
        )
    )
    assert executed["order"]["authorization_id"] == auth_id
    # 幂等：重复执行返回同一订单
    again = _ok(
        client.post(
            f"/api/inst/authorizations/{auth_id}/execute",
            json={"price": 100},
            headers=_h(execution),
        )
    )
    assert again.get("idempotent") is True

    reconciled = _ok(
        client.post(f"/api/inst/authorizations/{auth_id}/reconcile", headers=_h(execution))
    )
    assert reconciled["matched"] is True, reconciled
    with get_conn() as conn:
        exception = conn.execute(
            "INSERT INTO inst_execution_exception (org_id, authorization_id, type, detail) "
            "VALUES (%s,%s,'manual','对账差异待处理') RETURNING id",
            (fixture["org_id"], auth_id),
        ).fetchone()
    listed = _ok(client.get("/api/inst/execution/exceptions", headers=_h(execution)))
    assert any(item["id"] == exception["id"] for item in listed["items"])
    resolved = _ok(
        client.post(
            f"/api/inst/execution/exceptions/{int(exception['id'])}/resolve",
            json={"status": "resolved", "resolution": "已人工核对"},
            headers=_h(execution),
        )
    )
    assert resolved["status"] == "resolved"

    # 论点台账 + 复核 + 退出复盘
    thesis = _ok(
        client.post(
            "/api/inst/theses",
            json={
                "company_id": fixture["company_id"],
                "thesis": "品牌提价带来利润率修复",
                "kpis": [{"name": "毛利率", "target": 0.5}],
                "falsifiers": ["毛利率连续两季低于 30%"],
                "review_due": "2026-12-31",
            },
            headers=_h(manager),
        )
    )
    reviewed = _ok(
        client.post(
            f"/api/inst/theses/{int(thesis['id'])}/review",
            json={"kpi_status": "at_risk", "conclusion": "reduce", "note": "接近推翻线"},
            headers=_h(manager),
        )
    )
    assert reviewed["status"] == "reviewed"

    exit_case = _ok(
        client.post(
            "/api/inst/monitor/exits",
            json={"company_id": fixture["company_id"], "reason_type": "thesis_invalid", "memo": "论点失效"},
            headers=_h(manager),
        )
    )
    exit_id = int(exit_case["id"])
    review = _ok(
        client.post(
            f"/api/inst/monitor/exits/{exit_id}/review",
            json={"thesis_verdict": "wrong", "realized_return": -0.08, "holding_days": 30, "lessons": "高估提价"},
            headers=_h(manager),
        )
    )
    assert review["thesis_verdict"] == "wrong"

    # 风控阻断后 Chairman 不能再批准
    blocked_proposal = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/proposals",
            json={"direction": "buy", "target_weight": 0.30},
            headers=_h(manager),
        )
    )
    blocked_id = int(blocked_proposal["id"])
    _ok(
        client.post(
            f"/api/inst/proposals/{blocked_id}/partner",
            json={"decision": "approve", "updates": {"target_weight": 0.30}},
            headers=_h(partner),
        )
    )
    _ok(
        client.post(
            f"/api/inst/proposals/{blocked_id}/chairman",
            json={"decision": "approve"},
            headers=_h(chairman),
        )
    )
    risk_blocked = _ok(
        client.post(f"/api/inst/proposals/{blocked_id}/risk-check", json={}, headers=_h(risk))
    )
    assert risk_blocked["status"] == "frozen"
    assert (
        client.post(
            f"/api/inst/proposals/{blocked_id}/chairman",
            json={"decision": "approve"},
            headers=_h(chairman),
        ).status_code
        == 403
    )
