# -*- coding: utf-8 -*-
"""P1-D02：分钟频率回测基线。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.data.minute_backtest import run_minute_backtest  # noqa: E402


def _bars(n: int = 120, start: float = 10.0) -> list[dict]:
    out = []
    price = start
    for i in range(n):
        price += 0.02 if (i // 10) % 2 == 0 else -0.015
        out.append({"time": f"2026-09-10 {9 + i // 60:02d}:{i % 60:02d}:00", "close": price})
    return out


def test_backtest_produces_metrics() -> None:
    out = run_minute_backtest(_bars(), freq="1m", lookback=10, fee_rate=0.0003)
    assert out["ok"] and out["bars"] > 0
    assert out["metrics"]["trades"] >= 1
    assert out["metrics"]["max_drawdown"] <= 0
    assert out["frequency"] == "1m"


def test_backtest_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        run_minute_backtest(_bars(), freq="7m")
    with pytest.raises(ValueError):
        run_minute_backtest(_bars(5), lookback=20)
