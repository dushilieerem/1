# -*- coding: utf-8 -*-
"""机会发现立项三问与人工决策。

覆盖：
- 规则三问按资料状态给出 sufficient/partial/insufficient；
- 立项必须确认能力圈，资料缺失时只能观察/放弃；
- 观察、放弃都保留理由与操作人；
- 非投资经理不能做立项决策。
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

from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.institution import inst_service as svc  # noqa: E402
from services.institution.inst_schema import ensure_inst_business_schema  # noqa: E402
from services.institution.inst_store import ensure_inst_schema  # noqa: E402

ensure_schema()
ensure_inst_schema()
ensure_inst_business_schema()


def _mk_member(conn, org_id: int, role: str, tag: str) -> int:
    user = conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (%s,'!') RETURNING id",
        (f"inst_idea_{role}_{tag}",),
    ).fetchone()
    member = conn.execute(
        "INSERT INTO inst_members (org_id, user_id, role) VALUES (%s,%s,%s) RETURNING id",
        (org_id, int(user["id"]), role),
    ).fetchone()
    return int(member["id"])


@pytest.fixture(scope="module")
def fixture():
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"idea-{tag}", f"机会测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        manager_id = _mk_member(conn, org_id, "manager", tag)
        partner_id = _mk_member(conn, org_id, "partner", tag)
        cn = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, data_status, pool_status) "
            "VALUES (%s,%s,'资料齐全公司','CN','real','research') RETURNING id",
            (org_id, f"IDEA{tag[:4].upper()}.SH"),
        ).fetchone()
        partial = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, data_status, pool_status) "
            "VALUES (%s,%s,'部分资料公司','CN','partial','research') RETURNING id",
            (org_id, f"PART{tag[:4].upper()}.SH"),
        ).fetchone()
        us = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, data_status, pool_status) "
            "VALUES (%s,%s,'美股公司','US','missing','watch') RETURNING id",
            (org_id, f"US{tag[:4].upper()}"),
        ).fetchone()
    return {
        "org_id": org_id,
        "manager_id": manager_id,
        "partner_id": partner_id,
        "cn_id": int(cn["id"]),
        "partial_id": int(partial["id"]),
        "us_id": int(us["id"]),
    }


def test_idea_questions_by_data_sufficiency(fixture):
    with get_conn() as conn:
        cn = dict(conn.execute("SELECT * FROM inst_company WHERE id=%s", (fixture["cn_id"],)).fetchone())
        partial = dict(
            conn.execute("SELECT * FROM inst_company WHERE id=%s", (fixture["partial_id"],)).fetchone()
        )
        us = dict(conn.execute("SELECT * FROM inst_company WHERE id=%s", (fixture["us_id"],)).fetchone())

    cn_idea = svc._idea_questions(cn, "push", "近 5 日动量 3.2%")
    assert cn_idea["data_sufficiency"] == "sufficient"
    assert cn_idea["suggestion"] == "initiate"
    assert cn_idea["why_now"] == "近 5 日动量 3.2%"
    assert cn_idea["circle_of_competence"] == "unknown"

    partial_idea = svc._idea_questions(partial, "watch")
    assert partial_idea["data_sufficiency"] == "partial"
    assert partial_idea["suggestion"] == "watch"
    assert partial_idea["data_gaps"]

    us_idea = svc._idea_questions(us, "holdings")
    assert us_idea["data_sufficiency"] == "insufficient"
    assert us_idea["suggestion"] == "watch"
    assert any("美股/港股" in gap for gap in us_idea["data_gaps"])


def test_initiate_requires_circle_and_records_case(fixture):
    with pytest.raises(ValueError, match="能力圈"):
        svc.record_idea_decision(
            fixture["org_id"],
            fixture["cn_id"],
            source="push",
            action="initiate",
            reason="动量与估值通过，准备研究",
            circle_confirmed=False,
            actor_member_id=fixture["manager_id"],
        )

    out = svc.record_idea_decision(
        fixture["org_id"],
        fixture["cn_id"],
        source="push",
        action="initiate",
        reason="动量与估值通过，准备研究",
        circle_confirmed=True,
        actor_member_id=fixture["manager_id"],
    )
    assert out["pool_status"] == "research"
    assert out["case_id"]
    assert out["idea"]["data_sufficiency"] == "sufficient"
    with get_conn() as conn:
        company = conn.execute(
            "SELECT pool_status FROM inst_company WHERE id=%s", (fixture["cn_id"],)
        ).fetchone()
        decision = conn.execute(
            "SELECT action, reason, circle_confirmed FROM inst_idea_decision WHERE id=%s",
            (out["id"],),
        ).fetchone()
        case = conn.execute(
            "SELECT stage FROM inst_research_case WHERE id=%s", (out["case_id"],)
        ).fetchone()
    assert company["pool_status"] == "research"
    assert decision["action"] == "initiate"
    assert decision["circle_confirmed"] is True
    assert case["stage"] == "draft"


def test_missing_data_cannot_initiate(fixture):
    with pytest.raises(ValueError, match="核心资料缺失"):
        svc.record_idea_decision(
            fixture["org_id"],
            fixture["us_id"],
            source="holdings",
            action="initiate",
            reason="想复核一下",
            circle_confirmed=True,
            actor_member_id=fixture["manager_id"],
        )


def test_watch_and_reject_keep_reason(fixture):
    watched = svc.record_idea_decision(
        fixture["org_id"],
        fixture["partial_id"],
        source="watch",
        action="watch",
        reason="资料不完整，先观察季度数据",
        circle_confirmed=False,
        actor_member_id=fixture["manager_id"],
    )
    assert watched["pool_status"] == "watch"

    rejected = svc.record_idea_decision(
        fixture["org_id"],
        fixture["us_id"],
        source="watch",
        action="reject",
        reason="美股暂无基本面数据，放弃",
        circle_confirmed=False,
        actor_member_id=fixture["manager_id"],
    )
    assert rejected["pool_status"] == "dropped"

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT action, reason FROM inst_idea_decision WHERE company_id=%s ORDER BY id",
            (fixture["partial_id"],),
        ).fetchall()
        us = conn.execute(
            "SELECT pool_status, drop_reason FROM inst_company WHERE id=%s", (fixture["us_id"],)
        ).fetchone()
    assert rows[-1]["action"] == "watch"
    assert rows[-1]["reason"] == "资料不完整，先观察季度数据"
    assert us["pool_status"] == "dropped"
    assert us["drop_reason"] == "美股暂无基本面数据，放弃"


def test_reason_required_and_role_enforced(fixture):
    with pytest.raises(ValueError, match="决策理由"):
        svc.record_idea_decision(
            fixture["org_id"],
            fixture["partial_id"],
            source="watch",
            action="watch",
            reason="  ",
            circle_confirmed=False,
            actor_member_id=fixture["manager_id"],
        )
    with pytest.raises(PermissionError):
        svc.record_idea_decision(
            fixture["org_id"],
            fixture["partial_id"],
            source="watch",
            action="watch",
            reason="合伙人不能立项",
            circle_confirmed=False,
            actor_member_id=fixture["partner_id"],
        )
