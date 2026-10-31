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
