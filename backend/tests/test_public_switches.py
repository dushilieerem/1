# -*- coding: utf-8 -*-
"""公开运行开关：注册、文档、H5 模块下线。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.core.public_switches import disabled_modules, docs_enabled, registration_open  # noqa: E402


def test_defaults_are_open(monkeypatch) -> None:
    for key in ("SVQ_DOCS_ENABLED", "AUTH_REGISTRATION_OPEN", "INVEST_DISABLED_MODULES"):
        monkeypatch.delenv(key, raising=False)
    assert docs_enabled() is True
    assert registration_open() is True
    assert disabled_modules() == set()


def test_switches_can_close(monkeypatch) -> None:
    monkeypatch.setenv("SVQ_DOCS_ENABLED", "0")
    monkeypatch.setenv("AUTH_REGISTRATION_OPEN", "false")
    monkeypatch.setenv("INVEST_DISABLED_MODULES", "Stock, news ,,")
    assert docs_enabled() is False
    assert registration_open() is False
    assert disabled_modules() == {"stock", "news"}
