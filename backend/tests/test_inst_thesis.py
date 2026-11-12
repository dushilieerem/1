# -*- coding: utf-8 -*-
"""C4：投后台账（买入论点 / KPI / 复核 / 推翻条件 / 退出复盘）。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.institution.inst_schema import ensure_inst_business_schema  # noqa: E402
from services.institution.inst_service import (  # noqa: E402
    create_thesis,
    list_theses,
    review_exit,
    review_thesis,
)
from services.institution.inst_store import ensure_inst_schema  # noqa: E402

ensure_schema()
ensure_inst_schema()
ensure_inst_business_schema()


def _fixtures():
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        user = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s,'!') RETURNING id",
            (f"thesis_{tag}",),
        ).fetchone()
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"thesis-org-{tag}", f"台账测试 {tag}"),
        ).fetchone()
        member = conn.execute(
            "INSERT INTO inst_members (org_id, user_id, role) VALUES (%s,%s,'manager') RETURNING id",
            (org["id"], user["id"]),
        ).fetchone()
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name) VALUES (%s,%s,%s) RETURNING id",
            (org["id"], f"TEST{tag}.SH", f"测试公司 {tag}"),
        ).fetchone()
    return int(user["id"]), int(org["id"]), int(member["id"]), int(company["id"])


def test_thesis_lifecycle_and_exit_review() -> None:
    user_id, org_id, member_id, company_id = _fixtures()
    try:
        ledger = create_thesis(
            org_id,
            company_id=company_id,
            thesis="品牌提价与渠道改革带来利润率修复",
            key_assumptions=["出厂价年提 5%"],
            kpis=[{"name": "毛利率", "target": 0.5, "unit": "%"}],
            falsifiers=["毛利率连续两季低于 30%"],
            review_due="2026-12-31",
            actor_member_id=member_id,
        )
        assert ledger["status"] == "active"
        assert ledger["symbol"].startswith("TEST")

        reviewed = review_thesis(
            org_id,
            int(ledger["id"]),
            kpi_status="at_risk",
            conclusion="reduce",
            note="毛利率接近推翻线",
            actor_member_id=member_id,
        )
        assert reviewed["status"] == "reviewed"
        assert len(reviewed["reviews"]) == 1
        assert reviewed["reviews"][0]["kpi_status"] == "at_risk"

        assert any(t["id"] == ledger["id"] for t in list_theses(org_id))

        with pytest.raises(ValueError):
            create_thesis(org_id, company_id=company_id, thesis=" ", actor_member_id=member_id)
        with pytest.raises(ValueError):
            review_thesis(
                org_id,
                int(ledger["id"]),
                kpi_status="unknown",
                conclusion="hold",
                note=None,
                actor_member_id=member_id,
            )

        with get_conn() as conn:
            exit_case = conn.execute(
                "INSERT INTO inst_exit_case (org_id, company_id, reason_type, memo) "
                "VALUES (%s,%s,'thesis_invalid','毛利率跌破推翻线') RETURNING id",
                (org_id, company_id),
            ).fetchone()
        review = review_exit(
            org_id,
            int(exit_case["id"]),
            thesis_verdict="wrong",
            realized_return=-0.08,
            holding_days=120,
            lessons="高估提价能力",
            actor_member_id=member_id,
        )
        assert review["thesis_verdict"] == "wrong"
        assert review["holding_days"] == 120

        # WORM：审计记录不可篡改、不可删除
        with pytest.raises(Exception):
            with get_conn() as conn:
                conn.execute(
                    "UPDATE inst_audit_event SET action='tampered' WHERE org_id=%s", (org_id,)
                )
        with pytest.raises(Exception):
            with get_conn() as conn:
                conn.execute("DELETE FROM inst_audit_event WHERE org_id=%s", (org_id,))
    finally:
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
            conn.execute("DELETE FROM users WHERE id=%s", (user_id,))
