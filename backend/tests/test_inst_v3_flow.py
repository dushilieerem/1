# -*- coding: utf-8 -*-
"""v3 阶段机、研究/议案锁定与流水线 read model。"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import date, timedelta

import pytest

from services.core.db import get_conn
from services.institution import inst_service as svc

ORG_ID = 1


def _dims(low_key: str | None = None) -> list[dict]:
    out = []
    for key, title, _ in svc.SIX_DIM_DEFS:
        out.append({
            "key": key,
            "title": title,
            "status": "done",
            "summary": "结论",
            "rating": 2.0 if key == low_key else 4.0,
            "confidence": 0.8,
            "gate": "pass",
            "evidence_ids": [1],
            "counter": "反证",
        })
    return out


@contextmanager
def _case(*, dims: list[dict] | None = None):
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        member = conn.execute(
            "SELECT id FROM inst_members WHERE org_id=%s AND role='manager' AND status='active' LIMIT 1",
            (ORG_ID,),
        ).fetchone()["id"]
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market, industry, data_status, pool_status) "
            "VALUES (%s,%s,%s,'CN','测试','real','research') RETURNING id",
            (ORG_ID, f"T{tag}.SZ", f"测试公司{tag}"),
        ).fetchone()["id"]
        case = conn.execute(
            "INSERT INTO inst_research_case (org_id, company_id, case_no, stage, stage_no, stage_key, created_by) "
            "VALUES (%s,%s,%s,'pending_review',1,'research',%s) RETURNING id",
            (ORG_ID, company, f"RC-{tag}", member),
        ).fetchone()["id"]
        version = conn.execute(
            "INSERT INTO inst_research_version (case_id, version_no, status, six_dim, evidence_ids, content_hash, created_by) "
            "VALUES (%s,1,'pending_review',%s,'[1]'::jsonb,%s,%s) RETURNING id",
            (case, json.dumps(dims or _dims()), f"hash-{tag}", member),
        ).fetchone()["id"]
    try:
        yield {"org_id": ORG_ID, "member_id": int(member), "company_id": int(company), "case_id": int(case), "version_id": int(version)}
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM inst_approval WHERE proposal_version_id IN (SELECT id FROM inst_proposal_version WHERE proposal_id IN (SELECT id FROM inst_proposal WHERE case_id=%s))", (case,))
            conn.execute("DELETE FROM inst_authorization WHERE proposal_version_id IN (SELECT id FROM inst_proposal_version WHERE proposal_id IN (SELECT id FROM inst_proposal WHERE case_id=%s))", (case,))
            conn.execute("DELETE FROM inst_proposal_version WHERE proposal_id IN (SELECT id FROM inst_proposal WHERE case_id=%s)", (case,))
            conn.execute("DELETE FROM inst_proposal WHERE case_id=%s", (case,))
            conn.execute("DELETE FROM inst_debate_argument WHERE session_id IN (SELECT id FROM inst_debate_session WHERE case_id=%s)", (case,))
            conn.execute("DELETE FROM inst_debate_session WHERE case_id=%s", (case,))
            conn.execute("DELETE FROM inst_gate_run WHERE case_id=%s", (case,))
            conn.execute("DELETE FROM inst_case_transition WHERE case_id=%s", (case,))
            conn.execute("DELETE FROM inst_research_version WHERE case_id=%s", (case,))
            conn.execute("DELETE FROM inst_research_case WHERE id=%s", (case,))
            conn.execute("DELETE FROM inst_company WHERE id=%s", (company,))


def _add_debate(case_id: int, version_id: int, bull: int = 3, bear: int = 3) -> int:
    with get_conn() as conn:
        session = conn.execute(
            "INSERT INTO inst_debate_session (case_id, research_version_id, status, started_at, ended_at) "
            "VALUES (%s,%s,'completed',NOW(),NOW()) RETURNING id",
            (case_id, version_id),
        ).fetchone()["id"]
        for side, count in (("bull", bull), ("bear", bear)):
            for i in range(count):
                conn.execute(
                    "INSERT INTO inst_debate_argument (session_id, side, round, claim, evidence_ids, confidence, falsifier, valid) "
                    "VALUES (%s,%s,1,%s,'[1]'::jsonb,0.7,'反证',TRUE)",
                    (session, side, f"{side}-{i}"),
                )
    return int(session)


def test_pipeline_and_playbook() -> None:
    data = svc.pipeline(ORG_ID)
    assert len(data["stages"]) == 6
    assert [s["stage_no"] for s in data["stages"]] == [0, 1, 2, 3, 4, 5]
    book = svc.playbook()
    assert len(book["stages"]) == 6
    assert len(book["gates"]) == 3


def test_research_lock_and_reopen() -> None:
    with _case() as c:
        locked = svc.lock_research(c["org_id"], c["version_id"], actor_member_id=c["member_id"])
        assert locked["stage_no"] == 2
        assert locked["stage_key"] == "debate"
        assert locked["locks"]["research"]["version_id"] == c["version_id"]
        reopened = svc.reopen_research(c["org_id"], c["case_id"], reason="补数据", actor_member_id=c["member_id"])
        assert reopened["stage_no"] == 1
        assert reopened["stage_state"] == "returned"


def test_research_lock_blocks_low_confidence() -> None:
    with _case(dims=_dims(low_key="governance")) as c:
        with pytest.raises(PermissionError, match="研究门禁未通过"):
            svc.lock_research(c["org_id"], c["version_id"], actor_member_id=c["member_id"])


def test_proposal_lock_requires_debate_and_fields() -> None:
    with _case() as c:
        svc.lock_research(c["org_id"], c["version_id"], actor_member_id=c["member_id"])
        proposal = svc.create_proposal(
            c["org_id"], c["case_id"],
            actor_member_id=c["member_id"],
            direction="buy", target_weight=0.03, price_low=10, price_high=20,
            funding_source="现金",
            valid_until=(date.today() + timedelta(days=30)).isoformat(),
            monitoring=["季度复核"], investment_opinion="测试意见",
        )
        pid = int(proposal["id"])
        with pytest.raises(PermissionError, match="议案门禁未通过"):
            svc.submit_proposal(c["org_id"], pid, actor_member_id=c["member_id"])
        _add_debate(c["case_id"], c["version_id"])
        proposal2 = svc.create_proposal(
            c["org_id"], c["case_id"],
            actor_member_id=c["member_id"],
            direction="buy", target_weight=0.03, price_low=10, price_high=20,
            funding_source="现金",
            valid_until=(date.today() + timedelta(days=30)).isoformat(),
            monitoring=["季度复核"], investment_opinion="测试意见",
        )
        locked = svc.submit_proposal(c["org_id"], int(proposal2["id"]), actor_member_id=c["member_id"])
        assert locked["status"] == "partner_review"
        case = svc.get_case(c["org_id"], c["case_id"])
        assert case["stage_no"] == 3


def test_stage_summary_waits_for_all_approvers() -> None:
    rows = [{"step": "partner", "decision": "approve", "approver_member_id": 1, "conditions": []}]
    state = svc._stage_summary("partner", rows, 2)
    assert state["status"] == "in_progress"
    assert state["decided"] == 1 and state["required"] == 2
    rows.append({"step": "partner", "decision": "conditional", "approver_member_id": 2, "conditions": ["条件"]})
    state = svc._stage_summary("partner", rows, 2)
    assert state["status"] == "conditional"
    assert state["decided"] == 2
