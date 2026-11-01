# -*- coding: utf-8 -*-
"""R09 / FEAT-018：用户证券池与固定权重组合基准 CRUD/快照。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.research import asset_store as store  # noqa: E402

ensure_schema()


def _user() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s,'!') RETURNING id",
            (f"asset_{uuid.uuid4().hex[:8]}",),
        ).fetchone()
    return int(row["id"])


def test_universe_crud_and_versioning() -> None:
    user_id = _user()
    other_id = _user()
    try:
        universe = store.create_universe(
            user_id, name="消费龙头", symbols=["600519.SH", "000858.SZ", "600519.SH"]
        )
        assert universe["current_version"] == 1
        snap = universe["snapshot"]
        assert snap["membership_mode"] == "static"
        assert snap["symbols"] == ["000858.SZ", "600519.SH"]
        assert len(snap["content_hash"]) == 64

        same = store.update_universe(user_id, universe["id"], description="更新说明")
        assert same["current_version"] == 1 and same["changed"] is False

        changed = store.update_universe(
            user_id, universe["id"], symbols=["600519.SH", "000333.SZ"]
        )
        assert changed["current_version"] == 2 and changed["changed"] is True
        assert store.get_universe(user_id, universe["id"], version=1)["snapshot"]["symbols"] == [
            "000858.SZ",
            "600519.SH",
        ]

        assert len(store.list_universes(user_id)) == 1
        with pytest.raises(KeyError):
            store.get_universe(other_id, universe["id"])
        with pytest.raises(ValueError):
            store.create_universe(user_id, name="消费龙头", symbols=["000001.SZ"])
        with pytest.raises(ValueError):
            store.create_universe(user_id, name="坏代码", symbols=["600519"])
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id IN (%s,%s)", (user_id, other_id))


def test_benchmark_weights_and_snapshot() -> None:
    user_id = _user()
    try:
        with pytest.raises(ValueError):
            store.create_benchmark(user_id, name="坏权重", weights={"600519.SH": 0.6})
        with pytest.raises(ValueError):
            store.create_benchmark(
                user_id, name="负权重", weights={"600519.SH": 1.2, "000858.SZ": -0.2}
            )
        bench = store.create_benchmark(
            user_id,
            name="白酒 50/50",
            weights=[{"symbol": "600519.SH", "weight": 0.5}, {"symbol": "000858.SZ", "weight": 0.5}],
        )
        snap = bench["snapshot"]
        assert snap["pricing"] == "close_to_close"
        assert snap["weights"] == {"000858.SZ": 0.5, "600519.SH": 0.5}
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


def test_apply_asset_refs_replaces_legacy_params() -> None:
    user_id = _user()
    try:
        universe = store.create_universe(user_id, name="池", symbols=["600519.SH"])
        bench = store.create_benchmark(user_id, name="基准", weights={"600519.SH": 1.0})
        payload = store.apply_asset_refs(
            user_id,
            {
                "universe": "CSI300",
                "universe_asset_id": universe["id"],
                "benchmark": "CSI300",
                "benchmark_asset_id": bench["id"],
            },
        )
        assert "universe" not in payload and "benchmark" not in payload
        assert payload["universe_snapshot"]["symbols"] == ["600519.SH"]
        assert payload["benchmark_snapshot"]["weights"] == {"600519.SH": 1.0}
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id=%s", (user_id,))
