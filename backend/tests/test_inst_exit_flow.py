# -*- coding: utf-8 -*-
"""退出流程闭环：退出研究案 → 议案方向校验 → 审批/授权/执行状态机。

覆盖 FEAT-034 退出缺口的验收：
- 带退出案的研究案只能创建 sell/exit 议案，默认方向 exit、目标仓位 0。
- 退出案随议案提交、审批通过、授权、执行做合法状态迁移并写审计。
- 议案详情与投后列表能回链退出案、研究案与议案。
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
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
    user = _mk_user(conn, f"inst_exit_{role}_{tag}")
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
            (f"exit-{tag}", f"退出测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, ref_price) "
            "VALUES (%s,'600519.SH','贵州茅台','CN',100) RETURNING id",
            (org_id,),
        ).fetchone()
        portfolio = conn.execute(
            "INSERT INTO inst_portfolio (org_id, code, name, base_currency, nav, cash) "
            "VALUES (%s,'MAIN','退出测试组合','CNY',10000000,9000000) RETURNING id",
            (org_id,),
        ).fetchone()
        # 直接造一段持仓，退出案创建只依赖持仓快照。
        conn.execute(
            "INSERT INTO inst_position_snapshot "
            " (portfolio_id, symbol, qty, cost, market_value, weight, as_of) "
            "VALUES (%s,'600519.SH',1000,100,100000,0.01,%s)",
            (int(portfolio["id"]), date.today()),
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
        "portfolio_id": int(portfolio["id"]),
        "tokens": tokens,
        "members": members,
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
    assert resp.status_code == code, f"{resp.status_code} {resp.text[:300]}"
    return resp.json()


def _exit_status(fixture, exit_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM inst_exit_case WHERE id=%s AND org_id=%s",
            (exit_id, fixture["org_id"]),
        ).fetchone()
    assert row, "退出案不存在"
    return str(row["status"])


def _audit_actions(fixture, object_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT action FROM inst_audit_event WHERE org_id=%s AND object_type='inst_exit_case'"
            " AND object_id=%s ORDER BY id",
            (fixture["org_id"], object_id),
        ).fetchall()
    return [str(r["action"]) for r in rows]


def test_exit_flow_state_machine_and_direction_guard(fixture) -> None:
    tokens = fixture["tokens"]
    manager = tokens["manager"]
    client = TestClient(app)

    # 1) 投后发起退出：自动撤销旧授权并新建退出研究案。
    created = _ok(
        client.post(
            "/api/inst/monitor/exits",
            json={
                "company_id": fixture["company_id"],
                "reason_type": "thesis_invalid",
                "memo": "论点已被证伪",
            },
            headers=_h(manager),
        )
    )
    exit_id = int(created["id"])
    case_id = int(created["case_id"])
    assert created["status"] == "draft"

    # 研究 → 审核 → 辩论，走通退出研究案。
    research = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/research",
            json={"mode": "valuation"},
            headers=_h(manager),
        )
    )
    version_id = int(research["versions"][0]["id"])
    _ok(
        client.post(
            f"/api/inst/research/{version_id}/review",
            json={"decision": "approve", "comment": "退出研究通过"},
            headers=_h(tokens["partner"]),
        )
    )
    _ok(
        client.post(
            f"/api/inst/cases/{case_id}/debate",
            json={"use_ai": False},
            headers=_h(manager),
        )
    )

    # 2) 方向校验：退出案不能建买入议案。
    rejected = client.post(
        f"/api/inst/cases/{case_id}/proposals",
        json={"direction": "buy", "target_weight": 0.05},
        headers=_h(manager),
    )
    assert rejected.status_code == 400, rejected.text
    rejected_body = rejected.json()
    assert "退出研究案" in str(rejected_body.get("detail") or rejected_body), rejected.text
    assert _exit_status(fixture, exit_id) == "draft"

    # 3) 省略方向/仓位时默认 exit + 0（清仓），并迁移 draft → submitted。
    proposal = _ok(
        client.post(
            f"/api/inst/cases/{case_id}/proposals",
            json={},
            headers=_h(manager),
        )
    )
    proposal_id = int(proposal["id"])
    assert proposal["direction"] == "exit"
    assert float(proposal["target_weight"]) == 0.0
    assert int(proposal["exit_case"]["id"]) == exit_id
    assert _exit_status(fixture, exit_id) == "submitted"

    detail = _ok(client.get(f"/api/inst/proposals/{proposal_id}", headers=_h(manager)))
    assert detail["exit_case"]["case_id"] == case_id
    assert detail["exit_case"]["status"] == "submitted"

    # 4) 合伙人 → Chairman 审批：submitted → approved。
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
    assert _exit_status(fixture, exit_id) == "approved"

    # 5) 风控 → 授权：授权写审计，状态保持 approved。
    _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/risk-check",
            json={},
            headers=_h(tokens["risk"]),
        )
    )
    authorized = _ok(
        client.post(
            f"/api/inst/proposals/{proposal_id}/authorize",
            headers=_h(tokens["chairman"]),
        )
    )
    auth_id = int(authorized["authorizations"][0]["id"])
    assert _exit_status(fixture, exit_id) == "approved"

    # 6) 执行：approved → closed。
    executed = _ok(
        client.post(
            f"/api/inst/authorizations/{auth_id}/execute",
            json={"price": 100},
            headers=_h(tokens["execution"]),
        )
    )
    assert executed["order"]["side"] == "sell"
    assert _exit_status(fixture, exit_id) == "closed"

    # 7) 状态迁移与授权/执行都写审计，顺序可追溯。
    actions = _audit_actions(fixture, exit_id)
    assert actions == [
        "monitor.exit.create",
        "monitor.exit.submit",
        "monitor.exit.approve",
        "monitor.exit.authorize",
        "monitor.exit.close",
    ], actions

    # 8) 投后列表回链研究案/议案，并带议案与授权状态。
    monitor = _ok(client.get("/api/inst/monitor", headers=_h(tokens["monitoring"])))
    exit_row = next(x for x in monitor["exits"] if int(x["id"]) == exit_id)
    assert int(exit_row["case_id"]) == case_id
    assert exit_row["case_no"]
    assert int(exit_row["proposal_id"]) == proposal_id
    assert exit_row["proposal_status"] == "executed"
    assert exit_row["proposal_direction"] == "exit"
    assert exit_row["authorization_status"] == "filled"


def test_exit_case_off_flow_review_does_not_close_draft(fixture) -> None:
    """未走议案的退出案只写复盘，不产生非法状态迁移。"""
    tokens = fixture["tokens"]
    client = TestClient(app)
    # 上一用例已清仓，这里补回持仓，退出案创建只校验当前持仓数量。
    with get_conn() as conn:
        conn.execute(
            "UPDATE inst_position_snapshot SET qty=500, market_value=50000 "
            "WHERE portfolio_id=%s AND symbol='600519.SH'",
            (fixture["portfolio_id"],),
        )
    created = _ok(
        client.post(
            "/api/inst/monitor/exits",
            json={
                "company_id": fixture["company_id"],
                "reason_type": "valuation",
                "memo": "估值透支，先记录",
            },
            headers=_h(tokens["manager"]),
        )
    )
    exit_id = int(created["id"])
    review = _ok(
        client.post(
            f"/api/inst/monitor/exits/{exit_id}/review",
            json={"thesis_verdict": "mixed", "lessons": "等待正式议案"},
            headers=_h(tokens["manager"]),
        )
    )
    assert review["thesis_verdict"] == "mixed"
    assert _exit_status(fixture, exit_id) == "draft"
