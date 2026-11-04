# -*- coding: utf-8 -*-
"""P0-04：回测结果签名/验签（含跨 Python/JavaScript 规范化）。"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from services.strategy.result_signature import (
    PREFIX,
    _digest,
    _legacy_result_hash,
    result_hash,
    sign_result,
    verify_result,
)


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


def test_integral_floats_and_zero_match_json_numbers() -> None:
    assert result_hash(1) == result_hash(1.0)
    assert result_hash(0) == result_hash(0.0) == result_hash(-0.0)
    result = {"n": 954.0, "z": 0.0, "tz": -0.0, "one": 1.0}
    js_roundtrip = {"n": 954, "z": 0, "tz": 0, "one": 1}
    assert result_hash(result) == result_hash(js_roundtrip)


def test_legacy_token_still_verifies() -> None:
    # 旧版 Python-only 规范化签出的历史 token 必须继续可用。
    result = {"metrics": {"annual_return": 0.12}, "equity_curve": [1, 1.1]}
    legacy = PREFIX + _digest(7, _legacy_result_hash(result))
    assert verify_result(7, result, legacy)


def _node_roundtrip(tmp_path, result):
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用")
    src = tmp_path / "result.json"
    dst = tmp_path / "result.js.json"
    src.write_text(json.dumps({"result": result}, ensure_ascii=False), encoding="utf-8")
    script = (
        'const fs=require("fs");'
        'const d=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));'
        'fs.writeFileSync(process.argv[2],JSON.stringify(d.result));'
    )
    subprocess.run([node, "-e", script, str(src), str(dst)], check=True)
    return json.loads(dst.read_text(encoding="utf-8"))


def test_node_json_roundtrip_keeps_signature_verifiable(tmp_path) -> None:
    # 模拟真实浏览器：检测结果经 JSON.parse/JSON.stringify 后，整数浮点、
    # 0/-0、指数、精度都必须仍能验签。
    result = {
        "metrics": {
            "trade_count": 954.0,
            "annual_return": 0.1 + 0.2,
            "zero": 0.0,
            "negative_zero": -0.0,
            "tiny": 1e-7,
            "large": 1e20,
            "huge": 1e21,
        },
        "equity_curve": [
            {"value": 1.0, "drawdown": 0.0},
            {"value": 1.1, "drawdown": -0.04},
        ],
        "nested": [{"x": 1200.5}],
    }
    token = sign_result(7, result)

    roundtripped = _node_roundtrip(tmp_path, result)

    assert result_hash(roundtripped) == result_hash(result)
    assert verify_result(7, roundtripped, token)
