# -*- coding: utf-8 -*-
"""P1-F08：评价标准显式化与评价记录基础行为。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.crews.gather_idea.eval_agent import run_eval  # noqa: E402


def _report(**metrics) -> dict:
    return {"report_id": "r1", "metrics": metrics}


def test_review_when_metrics_pass_and_criteria_returned() -> None:
    out = run_eval(
        {"report": _report(sharpe=0.8, annual_return=0.12, max_drawdown=-0.2)},
        user_id=1,
    )
    assert out["verdict"] == "review"
    assert out["admit"] is False  # 自动评价永不直接入库
    assert [c["key"] for c in out["criteria"]] == [
        "sharpe",
        "annual_return",
        "max_drawdown",
        "verdict",
    ]


def test_reject_on_backtest_error() -> None:
    out = run_eval(
        {"report": {"report_id": "r2", "metrics": {}, "error": "boom"}}, user_id=1
    )
    assert out["verdict"] == "reject"
    assert any("回测报错" in r for r in out["reasons"])


def test_reject_when_metrics_are_weak() -> None:
    out = run_eval(
        {"report": _report(sharpe=0.1, annual_return=-0.05, max_drawdown=-0.6)},
        user_id=1,
    )
    assert out["verdict"] == "reject"
    assert out["admit"] is False
