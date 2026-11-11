# -*- coding: utf-8 -*-
"""聚宽策略直跑：预检、指纹与 RE payload。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.strategy.joinquant import (  # noqa: E402
    DIALECT_JOINQUANT,
    build_re_payload,
    code_hash,
    normalize_benchmark,
    normalize_dialect,
    precheck,
)

SAFE_CODE = '''
def initialize(context):
    run_daily(trade, time='09:30')

def trade(context):
    order_target_percent('600519.XSHG', 0.2)
'''


def test_normalize_dialect() -> None:
    assert normalize_dialect("joinquant") == DIALECT_JOINQUANT
    assert normalize_dialect("JOINQUANT") == DIALECT_JOINQUANT
    assert normalize_dialect("native") == "native"
    assert normalize_dialect(None) == "native"
    assert normalize_dialect("weird") == "native"


def test_code_hash_is_line_ending_stable() -> None:
    assert code_hash("a\nb") == code_hash("a\r\nb")
    assert code_hash("a\nb") == code_hash("  a\nb  ")


def test_precheck_empty_and_syntax() -> None:
    empty = precheck("")
    assert empty["can_run_directly"] is False
    assert empty["issues"][0]["code"] == "CODE-EMPTY"

    broken = precheck("def initialize(:\n  pass")
    assert broken["can_run_directly"] is False
    assert any(item["code"] == "CODE-SYNTAX" for item in broken["issues"])


def test_precheck_safe_strategy_can_run() -> None:
    out = precheck(SAFE_CODE)
    assert out["dialect"] == DIALECT_JOINQUANT
    assert out["engine"] == "event"
    assert out["can_run_directly"] is True
    assert out["blocker_count"] == 0
    assert out["code_hash"]


def test_precheck_blocks_unsupported_api() -> None:
    code = "def initialize(context):\n    get_call_auction('600519.XSHG')\n"
    out = precheck(code)
    assert out["can_run_directly"] is False
    assert out["blocker_count"] >= 1


def test_build_re_payload_fixed_dialect_params() -> None:
    payload = build_re_payload(
        source_code=SAFE_CODE, start="2024-01-01", end="2024-06-30", benchmark="000300.XSHG"
    )
    assert payload["engine_mode"] == "event"
    assert payload["strategy_dialect"] == "joinquant"
    assert payload["strategy_code"] == SAFE_CODE
    assert payload["execution_price_source"] == "unadjusted"
    assert payload["timed_execution"] is True
    assert payload["execution_timing"] == "next_open"
    # RE 的 benchmark 是枚举，聚宽写法要映射过去
    assert payload["benchmark"] == "CSI300"
    assert "universe" not in payload


def test_normalize_benchmark() -> None:
    assert normalize_benchmark("CSI300") == "CSI300"
    assert normalize_benchmark("csi500") == "CSI500"
    assert normalize_benchmark("000300.XSHG") == "CSI300"
    assert normalize_benchmark("000905.SH") == "CSI500"
    assert normalize_benchmark("") == "CSI300"
    assert normalize_benchmark(None) == "CSI300"
    try:
        normalize_benchmark("399001.SZ")
    except ValueError as exc:
        assert "CSI300" in str(exc)
    else:  # pragma: no cover - 必须拒绝不支持的基准，不能静默改成 CSI300
        raise AssertionError("不支持的 benchmark 应抛 ValueError")
