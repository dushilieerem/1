# -*- coding: utf-8 -*-
"""P0-04：回测结果签名/验签。"""
from __future__ import annotations

from services.strategy.result_signature import sign_result, verify_result


def test_sign_and_verify() -> None:
    result = {"metrics": {"annual_return": 0.12}, "equity_curve": [1, 1.1]}
    token = sign_result(7, result)
    assert verify_result(7, result, token)
    assert not verify_result(8, result, token)
    assert not verify_result(7, {"metrics": {"annual_return": 9.9}}, token)


def test_ignores_code_hash_and_token_fields() -> None:
    a = {"metrics": {"x": 1}, "code_hash": "abc", "_svquant_ui": {"x": 1}}
    b = {"metrics": {"x": 1}}
    token = sign_result(7, a)
    assert verify_result(7, b, token)
