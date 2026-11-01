# -*- coding: utf-8 -*-
"""R08 / FEAT-017：策略资产目录与版本化持久化验收。"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.strategy.user_strategy_library_store import (  # noqa: E402
    add_library_strategy,
    create_user_strategy_library,
    delete_user_strategy_library,
    get_library_strategy_version,
    list_library_strategy_versions,
    list_library_strategies,
    list_user_strategy_libraries,
    update_library_strategy,
)

ensure_schema()


def test_catalog_and_versions() -> None:
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        user = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s,'!') RETURNING id",
            (f"strat_{tag}",),
        ).fetchone()
    user_id = int(user["id"])
    library = create_user_strategy_library(user_id, f"库-{tag}")
    library_id = int(library["id"])
    try:
        assert any(lib["id"] == library_id for lib in list_user_strategy_libraries(user_id))

        strategy = add_library_strategy(
            user_id,
            library_id,
            name="双均线",
            body="class S:\n    def generate_signals(self):\n        return None\n",
            description="MA cross",
            category_label="趋势",
        )
        strategy_id = int(strategy["id"])
        assert any(s["id"] == strategy_id for s in list_library_strategies(user_id, library_id))

        versions = list_library_strategy_versions(user_id, strategy_id)
        assert [v["version_no"] for v in versions] == [1]

        updated = update_library_strategy(
            user_id,
            strategy_id,
            name="双均线 v2",
            body="class S:\n    def generate_signals(self):\n        return 2\n",
        )
        assert updated["name"] == "双均线 v2"
        versions = list_library_strategy_versions(user_id, strategy_id)
        assert [v["version_no"] for v in versions] == [2, 1]

        v1 = get_library_strategy_version(user_id, strategy_id, 1)
        assert v1["name"] == "双均线"
        assert "return None" in v1["body"]
        v2 = get_library_strategy_version(user_id, strategy_id, 2)
        assert "return 2" in v2["body"]

        with pytest.raises(KeyError):
            get_library_strategy_version(user_id, strategy_id, 99)
    finally:
        delete_user_strategy_library(user_id, library_id)
        with get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id=%s", (user_id,))
