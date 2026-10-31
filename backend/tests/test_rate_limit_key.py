# -*- coding: utf-8 -*-
"""P0-06：按 key 限流（供写接口中间件使用）。"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from services.core.rate_limit import enforce_rate_limit_key


def test_blocks_after_limit_and_sets_retry_after() -> None:
    key = f"test-{uuid.uuid4().hex}"
    enforce_rate_limit_key(key, scope="t", limit=1, window_sec=60)
    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit_key(key, scope="t", limit=1, window_sec=60)
    assert exc.value.status_code == 429
    assert exc.value.headers and "Retry-After" in exc.value.headers
