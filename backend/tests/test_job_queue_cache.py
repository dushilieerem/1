# -*- coding: utf-8 -*-
"""P1-O06：共享任务队列与缓存（需要 PostgreSQL）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.core import job_queue, shared_cache  # noqa: E402


def _db_ready() -> bool:
    try:
        job_queue.ensure_job_schema()
        shared_cache.ensure_cache_schema()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="需要 PostgreSQL")


def test_job_claim_complete() -> None:
    job_id = job_queue.enqueue("test.job", {"n": 1})
    job = job_queue.claim("test.job")
    assert job is not None
    job_queue.complete(int(job["id"]), {"ok": True})
    status = job_queue.job_status(job_id)
    assert status is not None and status["status"] == "done"


def test_cache_ttl_roundtrip() -> None:
    shared_cache.set("test:cache", {"v": 2}, ttl_sec=30)
    assert shared_cache.get("test:cache") == {"v": 2}
    shared_cache.delete("test:cache")
    assert shared_cache.get("test:cache") is None
