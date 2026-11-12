# -*- coding: utf-8 -*-
"""P1-A01/A02/C06/C07：会话标题、研究状态机、抓取重试与源授权清单。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.runtime import research_run_store as runs  # noqa: E402
from ai.runtime.conversation_store import _title  # noqa: E402
from services.news import news_ingest  # noqa: E402
from services.news.source_registry import list_sources  # noqa: E402


def test_conversation_title_truncates() -> None:
    assert _title("   ") == "新会话"
    assert _title("a" * 100).__len__() <= 60
    assert _title("多行\n标题") == "多行 标题"


def test_research_state_machine() -> None:
    status, step = runs.transition(
        current_step="gather", step="gather", approve=False, fail=None, status="running"
    )
    assert (status, step) == ("running", "idea")
    # 回测/报告需要人工确认，未确认则停在等待态
    status, step = runs.transition(
        current_step="backtest", step="backtest", approve=False, fail=None, status="running"
    )
    assert (status, step) == ("waiting_confirmation", "backtest")
    status, step = runs.transition(
        current_step="backtest", step="backtest", approve=True, fail=None, status="running"
    )
    assert (status, step) == ("running", "eval")
    status, step = runs.transition(
        current_step="report", step="report", approve=True, fail=None, status="running"
    )
    assert status == "completed"
    with pytest.raises(ValueError):
        runs.transition(current_step="idea", step="gather", approve=False, fail=None, status="running")


def test_retry_config_bounds(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.core.env_config.env",
        lambda k, d=None: {"NEWS_FETCH_RETRIES": "99", "NEWS_FETCH_BACKOFF_SEC": "-1"}.get(k, d),
    )
    retries, backoff = news_ingest._retry_config()
    assert retries == 5
    assert backoff == 0.0


def test_source_registry_marks_blocked() -> None:
    data = list_sources()
    by_id = {s["id"]: s for s in data["items"]}
    assert by_id["bloomberg"]["authorization"] == "blocked"
    assert data["counts"]["blocked"] == 1
