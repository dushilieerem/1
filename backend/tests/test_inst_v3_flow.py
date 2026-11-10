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
from services.institution import ai_service as inst_ai

ORG_ID = 0


@pytest.fixture(scope="module", autouse=True)
def _v3_org():
    """自建测试机构，不依赖演示种子或固定 ID。"""
    global ORG_ID
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"v3-{tag}", f"v3 流程测试机构 {tag}"),
        ).fetchone()
        ORG_ID = int(org["id"])
        user_ids: list[int] = []
        for role in ("manager", "partner", "risk", "chairman", "execution", "monitoring"):
            user = conn.execute(
                "INSERT INTO users (username, password_hash, role, status, display_name) "
                "VALUES (%s,'x','user','active',%s) RETURNING id",
                (f"v3_{role}_{tag}", f"v3 测试{role} {tag}"),
            ).fetchone()
            user_ids.append(int(user["id"]))
            conn.execute(
                "INSERT INTO inst_members (org_id, user_id, role, title_cn, status) "
                "VALUES (%s,%s,%s,%s,'active')",
                (ORG_ID, int(user["id"]), role, f"测试{role}"),
            )
    yield ORG_ID
    with get_conn() as conn:
        conn.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='inst_audit_event_worm')"
            " THEN ALTER TABLE inst_audit_event DISABLE TRIGGER inst_audit_event_worm; END IF; END $$"
        )
        conn.execute("DELETE FROM inst_orgs WHERE id=%s", (ORG_ID,))
        conn.execute("DELETE FROM users WHERE id = ANY(%s)", (user_ids,))
        conn.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='inst_audit_event_worm')"
            " THEN ALTER TABLE inst_audit_event ENABLE TRIGGER inst_audit_event_worm; END IF; END $$"
        )


def _dims(low_key: str | None = None) -> list[dict]:
    out = []
    for key, title, _ in svc.SIX_DIM_DEFS:
        out.append({
            "key": key,
            "title": title,
            "status": "done",
            "summary": "结论",
            "rating": 2.0 if key == low_key else 4.0,
            "rating_benchmark": "同业中位 3.8/5",
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


def test_closed_cases_excluded_from_lists_and_pipeline() -> None:
    with _case() as c:
        with get_conn() as conn:
            conn.execute(
                "UPDATE inst_research_case SET stage='closed', stage_state='closed' WHERE id=%s",
                (c["case_id"],),
            )
        ids = {int(x["id"]) for x in svc.list_cases(c["org_id"])}
        assert c["case_id"] not in ids
        pipeline_ids = {
            int(item["case_id"])
            for stage in svc.pipeline(c["org_id"])["stages"]
            for item in stage["items"]
            if item.get("case_id")
        }
        assert c["case_id"] not in pipeline_ids


def test_pipeline_per_stage_limit(monkeypatch) -> None:
    monkeypatch.setenv("INST_PIPELINE_PER_STAGE", "3")
    data = svc.pipeline(ORG_ID)
    for stage in data["stages"]:
        assert len(stage["items"]) <= 3
        assert stage["count"] == len(stage["items"])
    assert data["total"] <= 18


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


def test_research_gate_preview_and_dimension_review() -> None:
    with _case(dims=_dims(low_key="governance")) as c:
        gate = svc.research_gate(c["org_id"], c["version_id"])
        assert gate["status"] == "block"
        assert any(
            x["key"] == "low_confidence" and x["status"] == "block"
            for x in gate["checks"]
        )
        svc.review_research_dimension(
            c["org_id"],
            c["version_id"],
            "governance",
            decision="approve",
            comment="已核对原始公告",
            actor_member_id=c["member_id"],
        )
        gate_after = svc.research_gate(c["org_id"], c["version_id"])
        assert gate_after["status"] == "pass"
        locked = svc.lock_research(
            c["org_id"], c["version_id"], actor_member_id=c["member_id"]
        )
        assert locked["stage_no"] == 2


def test_opportunity_source_labels() -> None:
    from services.institution.research_service import _opportunity_source

    push = _opportunity_source(
        {"research_points": ["近 5 日动量 3.2%"], "pool_status": "watch"},
        "push",
    )
    assert push["source_label"] == "量化策略推送"
    assert push["source_detail"] == "近 5 日动量 3.2%"
    watch = _opportunity_source({"pool_status": "watch"}, "watch")
    assert watch["source_label"] == "自选"
    assert "自选" in watch["source_detail"]


def test_proposal_advice_lists_scores_debate_and_framework() -> None:
    with _case() as c:
        _add_debate(c["case_id"], c["version_id"])
        advice = svc.proposal_advice(c["org_id"], c["case_id"])
        assert len(advice["scores"]) == 6
        assert advice["overall_score"] == 8.0
        assert advice["debate"]["bull_count"] == 3
        assert advice["debate"]["bear_count"] == 3
        assert advice["recommendation"] in {"buy", "sell", "hold", "avoid"}
        assert advice["recommendation_label"]
        framework = advice["framework"]
        assert framework["direction"] in {"buy", "sell", "exit"}
        assert 0 <= float(framework["target_weight"]) <= 1
        assert len(str(framework["investment_opinion"])) >= 60
        assert framework["monitoring"]


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


def test_approval_memo_cached_only_never_calls_ai(monkeypatch) -> None:
    with _case() as c:
        svc.lock_research(c["org_id"], c["version_id"], actor_member_id=c["member_id"])
        _add_debate(c["case_id"], c["version_id"])
        proposal = svc.create_proposal(
            c["org_id"],
            c["case_id"],
            actor_member_id=c["member_id"],
            direction="buy",
            target_weight=0.03,
            price_low=10,
            price_high=20,
            funding_source="现金",
            valid_until=(date.today() + timedelta(days=30)).isoformat(),
            monitoring=["季度复核"],
            investment_opinion="测试意见",
        )
        pid = int(proposal["id"])
        svc.submit_proposal(c["org_id"], pid, actor_member_id=c["member_id"])
        with get_conn() as conn:
            partner_id = int(
                conn.execute(
                    "SELECT id FROM inst_members WHERE org_id=%s AND role='partner' AND status='active' LIMIT 1",
                    (c["org_id"],),
                ).fetchone()["id"]
            )

        def _must_not_run(*args, **kwargs):
            raise AssertionError("cached_only 不应调用 AI")

        monkeypatch.setattr(inst_ai, "_ai_task", _must_not_run)
        out = svc.ai_partner_memo(
            c["org_id"], pid, actor_member_id=partner_id, cached_only=True
        )
        assert out["memo"] is None
        assert out["missing"] is True


def test_memo_syncs_version_conclusion(monkeypatch) -> None:
    with _case() as c:
        def _unavailable(*args, **kwargs):
            raise svc.AiUnavailable("AI 未配置")

        monkeypatch.setattr(inst_ai, "_ai_task", _unavailable)
        out = svc.ai_research_memo(
            c["org_id"], c["case_id"], actor_member_id=c["member_id"]
        )
        assert out["memo"]["conclusion"]
        case = svc.get_case(c["org_id"], c["case_id"])
        assert case["versions"][0]["conclusion"] == out["memo"]["conclusion"]
        assert case["versions"][0]["content_hash"] is None


def test_search_and_start_research_reuses_current_case() -> None:
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        member_id = int(
            conn.execute(
                "SELECT id FROM inst_members WHERE org_id=%s AND role='manager' AND status='active' LIMIT 1",
                (ORG_ID,),
            ).fetchone()["id"]
        )
        company_id = int(
            conn.execute(
                "INSERT INTO inst_company (org_id, symbol, name, market, industry, data_status, pool_status) "
                "VALUES (%s,%s,%s,'CN','测试','real','watch') RETURNING id",
                (ORG_ID, f"SEARCH{tag[:4].upper()}.SZ", f"搜索测试{tag}"),
            ).fetchone()["id"]
        )
    try:
        items = svc.search_companies(ORG_ID, f"SEARCH{tag[:4].upper()}", limit=5)
        assert items and items[0]["company_id"] == company_id
        assert items[0]["case_id"] is None

        first = svc.start_research(ORG_ID, company_id, member_id)
        assert first["created"] is True
        assert first["company_id"] == company_id
        second = svc.start_research(ORG_ID, company_id, member_id)
        assert second["created"] is False
        assert second["id"] == first["id"]
        with get_conn() as conn:
            row = conn.execute(
                "SELECT pool_status FROM inst_company WHERE id=%s", (company_id,)
            ).fetchone()
            assert row["pool_status"] == "research"
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM inst_research_case WHERE company_id=%s", (company_id,))
            conn.execute("DELETE FROM inst_company WHERE id=%s", (company_id,))


def test_stage_summary_waits_for_all_approvers() -> None:
    rows = [{"step": "partner", "decision": "approve", "approver_member_id": 1, "conditions": []}]
    state = svc._stage_summary("partner", rows, 2)
    assert state["status"] == "in_progress"
    assert state["decided"] == 1 and state["required"] == 2
    rows.append({"step": "partner", "decision": "conditional", "approver_member_id": 2, "conditions": ["条件"]})
    state = svc._stage_summary("partner", rows, 2)
    assert state["status"] == "conditional"
    assert state["decided"] == 2


def test_delete_case_archives_and_allows_new_case() -> None:
    with _case() as c:
        out = svc.delete_case(ORG_ID, c["case_id"], c["member_id"])
        assert out["deleted"] is True
        assert c["case_id"] not in {int(x["id"]) for x in svc.list_cases(ORG_ID)}
        with get_conn() as conn:
            row = conn.execute(
                "SELECT stage, stage_state, terminal_reason FROM inst_research_case WHERE id=%s",
                (c["case_id"],),
            ).fetchone()
            assert row["stage"] == "closed"
            assert row["stage_state"] == "closed"
            assert row["terminal_reason"] == "deleted_by_user"
            company = conn.execute(
                "SELECT pool_status FROM inst_company WHERE id=%s", (c["company_id"],)
            ).fetchone()
            assert company["pool_status"] == "dropped"
        new = svc.start_research(ORG_ID, c["company_id"], c["member_id"])
        assert new["created"] is True
        assert new["id"] != c["case_id"]
        with get_conn() as conn:
            conn.execute("DELETE FROM inst_research_case WHERE id=%s", (new["id"],))


def test_delete_case_blocks_execution_stage() -> None:
    with _case() as c:
        with get_conn() as conn:
            conn.execute(
                "UPDATE inst_research_case SET stage='approved', stage_no=4 WHERE id=%s",
                (c["case_id"],),
            )
        with pytest.raises(ValueError, match="执行/投后"):
            svc.delete_case(ORG_ID, c["case_id"], c["member_id"])


def test_generate_research_skips_dimensions_without_data(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("没有数据的维度不应调用 Agent")

    monkeypatch.setattr(svc, "_run_dimension_agents", _boom)
    monkeypatch.setattr(svc, "_run_industry_agent", _boom)
    with _case() as c:
        out = svc.generate_research(
            ORG_ID, c["case_id"], mode="full", actor_member_id=c["member_id"]
        )
        version = out["versions"][0]
        dims = version["six_dim"]
        assert len(dims) == 6
        assert all(d["status"] == "skipped" for d in dims)
        assert all(d["score_10"] is None and d["rating"] is None for d in dims)
        assert all(d["summary"] == "数据未接入，暂不分析。" for d in dims)
        assert version["industry_analysis"]["status"] == "skipped"


def test_proposal_advice_scores_latest_rating_without_benchmark() -> None:
    dims = [
        {
            "key": key,
            "title": title,
            "status": "partial",
            "summary": "结论",
            "rating": 2.5,
            "score_10": None,
            "rating_benchmark": None,
            "confidence": 0.6,
            "gate": "fail" if key == "governance" else "watch",
        }
        for key, title, _ in svc.SIX_DIM_DEFS
    ]
    with _case(dims=dims) as c:
        advice = svc.proposal_advice(c["org_id"], c["case_id"])
        assert [x["score_10"] for x in advice["scores"]] == [5.0] * 6
        assert advice["overall_score"] == 5.0
        assert advice["recommendation"] == "avoid"
        assert advice["framework"]["direction"] == "hold"
