# -*- coding: utf-8 -*-
"""C2：AI Chairman 预检查 / 模拟批准判定。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.institution.chairman_mode import evaluate  # noqa: E402

SNAPSHOT = {"qty": 300, "price": 1392.05, "price_low": 1300, "price_high": 1450, "currency": "CNY"}


def _eval(**kw):
    base = {
        "proposal_status": "chairman_review",
        "snapshot": SNAPSHOT,
        "approvals": {
            "partner": {"decision": "approve"},
            "risk_precheck": {"decision": "pass"},
        },
        "risk_checks": [{"key": "weight", "label": "单股 ≤15%", "status": "pass"}],
        "evidence_count": 3,
        "ai_available": True,
        "proposer_is_reviewer": False,
    }
    base.update(kw)
    return evaluate(**base)


def test_all_green_is_approve_candidate_but_never_binding() -> None:
    out = _eval()
    assert out["ready"] is True
    assert out["recommendation"] == "approve_candidate"
    assert out["binding"] is False
    assert out["requires_human"] is True
    assert out["blocking"] == []


def test_missing_partner_blocks() -> None:
    out = _eval(approvals={"risk_precheck": {"decision": "pass"}})
    assert out["ready"] is False
    assert out["recommendation"] == "human_required"
    assert "partner" in out["blocking"]


def test_risk_block_blocks() -> None:
    out = _eval(risk_checks=[{"key": "cash", "label": "交易后现金 ≥10%", "status": "block"}])
    assert out["ready"] is False
    assert "risk_items" in out["blocking"]


def test_warnings_make_it_conditional() -> None:
    out = _eval(snapshot={**SNAPSHOT, "currency": "USD"}, ai_available=False)
    assert out["ready"] is True
    assert out["recommendation"] == "conditional_candidate"
    assert set(out["warnings"]) >= {"currency", "ai"}


def test_proposer_cannot_review() -> None:
    out = _eval(proposer_is_reviewer=True)
    assert out["ready"] is False
    assert "proposer" in out["blocking"]
