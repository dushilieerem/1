# -*- coding: utf-8 -*-
"""P1-A07：AI 离线评测集与回归门槛。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.evals.run import load_cases, run  # noqa: E402


def test_bundled_cases_all_pass() -> None:
    report = run(load_cases())
    assert report["total"] >= 5
    assert report["ok"], [r for r in report["results"] if not r["ok"]]


def test_runner_detects_expectation_mismatch() -> None:
    report = run(
        [
            {
                "id": "should-fail",
                "kind": "json_keys",
                "payload": {"a": 1},
                "required": ["b"],
                "expect_ok": True,
            }
        ]
    )
    assert report["ok"] is False
    assert report["results"][0]["expected_ok"] is True
    assert report["results"][0]["actual_ok"] is False
