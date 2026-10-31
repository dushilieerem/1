# -*- coding: utf-8 -*-
"""P2-07：分享代码脱敏。"""
from __future__ import annotations

from services.strategy.strategy_plaza_store import _scrub_secrets


def test_scrubs_api_keys_and_bearer() -> None:
    raw = 'KEY="sk-abcdefghijklmnopqrstuvwxyz"\nheader = "Bearer abcdefghijklmnopqrstuvwxyz"\napi_key="hello"'
    out = _scrub_secrets(raw)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in out
    assert "Bearer abcdefghijklmnopqrstuvwxyz" not in out
    assert "hello" not in out
    assert "***" in out
