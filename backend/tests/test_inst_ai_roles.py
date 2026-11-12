# -*- coding: utf-8 -*-
"""I01–I06：机构端 AI 岗位目录与调度。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.institution import inst_service as svc  # noqa: E402


def test_catalog_has_six_roles() -> None:
    items = svc.ai_role_catalog()
    assert [i["key"] for i in items] == [
        "research",
        "financial",
        "governance",
        "debate",
        "risk",
        "post_investment",
    ]
    assert all(i["task"].startswith("inst.") for i in items)


def test_new_role_uses_task_and_returns_memo(monkeypatch) -> None:
    monkeypatch.setattr(svc, "_role_case_payload", lambda org_id, case_id: {"company": {"symbol": "600519.SH"}})
    monkeypatch.setattr(
        svc,
        "_ai_task",
        lambda task_id, payload, system: {"summary": f"{task_id} ok", "evidence": [], "risks": [], "open_questions": []},
    )
    out = svc.ai_role_run(1, "financial", case_id=7)
    assert out["role"] == "financial"
    assert out["task"] == "inst.role.financial"
    assert out["memo"]["summary"] == "inst.role.financial ok"


def test_reuses_existing_tasks(monkeypatch) -> None:
    monkeypatch.setattr(svc, "ai_research_memo", lambda org_id, case_id: {"memo": {"summary": "r"}})
    monkeypatch.setattr(
        svc, "start_debate", lambda org_id, case_id, actor_member_id=None, use_ai=True: {"ok": True}
    )
    monkeypatch.setattr(svc, "ai_risk_review", lambda org_id, proposal_id: {"memo": {"summary": "k"}})
    assert svc.ai_role_run(1, "research", case_id=7)["result"]["memo"]["summary"] == "r"
    assert svc.ai_role_run(1, "debate", case_id=7)["result"]["ok"] is True
    assert svc.ai_role_run(1, "risk", proposal_id=9)["result"]["memo"]["summary"] == "k"


def test_validation() -> None:
    with pytest.raises(ValueError):
        svc.ai_role_run(1, "unknown", case_id=1)
    with pytest.raises(ValueError):
        svc.ai_role_run(1, "financial")
    with pytest.raises(ValueError):
        svc.ai_role_run(1, "risk")
