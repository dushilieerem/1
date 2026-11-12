# -*- coding: utf-8 -*-
"""P1-F09：检测结果签名校验。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.routers.factor import _sign_factor_result  # noqa: E402
from services.factor.detect_store import _verified_detect_result  # noqa: E402
from services.strategy.result_signature import sign_result  # noqa: E402

RESULT = {"metrics": {"ic": 0.05}, "status": "done"}


def test_async_succeeded_result_is_signed_and_verifies() -> None:
    # RE 异步轮询：结果在嵌套 result 里，前端只把这个对象带去落库。
    task = {"status": "succeeded", "run_id": "run-1", "result": dict(RESULT)}

    signed = _sign_factor_result(7, 200, task)

    assert signed["run_id"] == "run-1"
    assert signed["status"] == "succeeded"
    assert "_svquant_verified_token" in signed["result"]
    out = _verified_detect_result(7, signed["result"])
    assert out["_svquant_verified"] is True
    assert "_svquant_verified_token" not in out


def test_running_task_is_not_signed() -> None:
    task = {"status": "running", "run_id": "run-1"}

    assert _sign_factor_result(7, 200, task) == task


def test_valid_signature_marks_verified_and_drops_token() -> None:
    payload = {**RESULT, "_svquant_verified_token": sign_result(7, RESULT)}
    out = _verified_detect_result(7, payload)
    assert out["_svquant_verified"] is True
    assert "_svquant_verified_token" not in out


def test_invalid_signature_is_rejected() -> None:
    payload = {**RESULT, "_svquant_verified_token": sign_result(8, RESULT)}
    with pytest.raises(ValueError, match="签名无效"):
        _verified_detect_result(7, payload)


def test_missing_signature_is_saved_unverified() -> None:
    out = _verified_detect_result(7, RESULT)
    assert out["_svquant_verified"] is False
