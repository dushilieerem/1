# -*- coding: utf-8 -*-
"""P1-F09：检测结果签名校验。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factor.detect_store import _verified_detect_result  # noqa: E402
from services.strategy.result_signature import sign_result  # noqa: E402

RESULT = {"metrics": {"ic": 0.05}, "status": "done"}


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
