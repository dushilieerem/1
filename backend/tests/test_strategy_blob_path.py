# -*- coding: utf-8 -*-
"""P0-01：策略结果 blob 路径穿越回归。"""
from __future__ import annotations

import pytest

from services.strategy.strategy_store import _blob_path


def test_valid_run_id_path() -> None:
    path = _blob_path(7, "8f14e45f-ea8c-4c1d-9b2a-123456789abc")
    assert path.name.endswith(".json.gz")
    assert path.parent.name == "7"


@pytest.mark.parametrize("bad", ["../secret", "..%2fsecret", "a/b", "", "x" * 81, "a.b"])
def test_rejects_path_traversal(bad: str) -> None:
    with pytest.raises(ValueError):
        _blob_path(7, bad)
