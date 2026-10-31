# -*- coding: utf-8 -*-
"""P1-A05：平台引用服务端回查。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.community import platform_ref_verify as verify  # noqa: E402


def _ref(**metrics) -> dict:
    return {
        "source": "factor_detect",
        "ref_id": "run-1",
        "metrics": metrics,
        "metrics_display": {},
    }


def test_matching_metrics_are_verified(monkeypatch) -> None:
    monkeypatch.setattr(
        verify,
        "_load_run",
        lambda uid, source, rid: {"result": {"metrics": {"sharpe": 0.8, "annual_return": 0.12}}},
    )
    out = verify.verify_platform_ref(1, _ref(sharpe=0.8001, annual_return=0.1202))
    assert out["metrics_verified"] is True


def test_mismatched_metrics_are_flagged(monkeypatch) -> None:
    monkeypatch.setattr(
        verify,
        "_load_run",
        lambda uid, source, rid: {"result": {"metrics": {"sharpe": 0.2}}},
    )
    out = verify.verify_platform_ref(1, _ref(sharpe=1.9))
    assert out["metrics_verified"] is False
    assert "不一致" in out["verify_note"]


def test_missing_run_id_is_unverified() -> None:
    ref = {"source": "strategy_report", "metrics": {"sharpe": 1.0}}
    out = verify.verify_platform_ref(1, ref)
    assert out["metrics_verified"] is False
    assert "运行 id" in out["verify_note"]


def test_unknown_source_is_unverified() -> None:
    out = verify.verify_platform_ref(1, {"source": "manual", "metrics": {}})
    assert out["metrics_verified"] is False
