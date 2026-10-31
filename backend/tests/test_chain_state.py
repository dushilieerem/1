# -*- coding: utf-8 -*-
"""P1-F07：研究链快照合并语义。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.runtime.chain_store import merge_chain_state  # noqa: E402


def test_only_patched_sections_change() -> None:
    current = {"idea": {"a": 1}, "draft": {"b": 2}, "report": {"c": 3}, "updated_at": "x"}
    merged = merge_chain_state(current, {"draft": {"b": 9}})
    assert merged["idea"] == {"a": 1}
    assert merged["draft"] == {"b": 9}
    assert merged["report"] == {"c": 3}


def test_explicit_null_clears_section() -> None:
    merged = merge_chain_state({"idea": {"a": 1}, "draft": {"b": 2}}, {"draft": None})
    assert merged["draft"] is None
    assert merged["idea"] == {"a": 1}


def test_empty_patch_keeps_state() -> None:
    current = {"idea": {"a": 1}}
    assert merge_chain_state(current, {}) == current
