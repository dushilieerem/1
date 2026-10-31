# -*- coding: utf-8 -*-
"""P0-14：因子目录 primary/all 双 scope 一致性检查。"""
from __future__ import annotations

import time

from services.factor import re_factor_catalog as catalog


def test_scope_status_detects_stale_and_count_mismatch(monkeypatch) -> None:
    now = int(time.time())

    def fake_load(include_all: bool):
        if include_all:
            return {"factors": [{"id": "a"}], "content_hash": "all", "fetched_at": "now", "fetched_at_unix": now}
        return {"factors": [{"id": "a"}, {"id": "b"}], "content_hash": "pri", "fetched_at": "old", "fetched_at_unix": now - 8 * 24 * 3600}

    monkeypatch.setattr(catalog, "_load_db", fake_load)
    status = catalog.catalog_scope_status()
    assert status["ok"] is False
    assert any("primary" in w for w in status["warnings"])


def test_scope_status_ok(monkeypatch) -> None:
    now = int(time.time())

    def fake_load(include_all: bool):
        return {"factors": [{"id": "a"}], "content_hash": "x", "fetched_at": "now", "fetched_at_unix": now}

    monkeypatch.setattr(catalog, "_load_db", fake_load)
    assert catalog.catalog_scope_status()["ok"] is True


def _factor(lib: str, name: str) -> dict:
    return {"library": lib, "name": name}


def test_factor_diff_reports_added_and_removed() -> None:
    old = {"factors": [_factor("A", "f1"), _factor("A", "f2")]}
    new = {"factors": [_factor("A", "f2"), _factor("A", "f3"), _factor("B", "f1")]}
    diff = catalog.factor_diff(old, new)
    assert diff["first_sync"] is False
    assert diff["added_count"] == 2
    assert diff["removed_count"] == 1
    assert diff["added"] == ["A::f3", "B::f1"]
    assert diff["removed"] == ["A::f1"]


def test_factor_diff_first_sync_is_not_a_change() -> None:
    diff = catalog.factor_diff(None, {"factors": [_factor("A", "f1")]})
    assert diff["first_sync"] is True
    assert diff["added_count"] == 1
    assert diff["removed_count"] == 0


def test_sync_status_includes_recent_syncs(monkeypatch) -> None:
    monkeypatch.setattr(
        catalog,
        "catalog_scope_status",
        lambda: {"ok": True, "scopes": {}, "warnings": []},
    )
    monkeypatch.setattr(
        catalog,
        "sync_log",
        lambda limit=20: [{"scope": "all", "changed": True, "detail": {"added_count": 1}}],
    )
    status = catalog.catalog_sync_status(limit=5)
    assert status["ok"] is True
    assert status["recent_syncs"][0]["detail"]["added_count"] == 1
