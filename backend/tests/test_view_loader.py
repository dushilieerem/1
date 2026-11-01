# -*- coding: utf-8 -*-
"""M01：视图 → PG 服务表的字段映射与清洗。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.data import view_loader as loader  # noqa: E402


def test_period_and_day() -> None:
    assert loader._period("20250331") == "2025Q1"
    assert loader._period("20251231") == "2025Q4"
    assert loader._period("bad") == "bad"
    assert loader._iso_day("20260417") == "2026-04-17"
    assert loader._iso_day(None) is None


def test_clean_nan_to_none() -> None:
    assert loader._clean(float("nan")) is None
    assert loader._clean(1.5) == 1.5
    assert loader._clean(None) is None


def test_valuation_frame_maps_and_filters(monkeypatch) -> None:
    import pyarrow as pa

    table = pa.table(
        {
            "date": ["2026-10-30", "2026-10-01"],
            "symbol": ["600519.SH", "600519.SH"],
            "pe_ttm": [21.3, 22.0],
            "pb_mrq": [6.9, 7.0],
            "pcf_operating_cash_flow_ttm": [14.6, 15.0],
            "dividend_yield_ttm": [3.73, 3.8],
            "float_mv": [None, 1.0],
            "total_mv": [1.74e12, 1.8e12],
        }
    )
    monkeypatch.setattr(loader, "view_root", lambda: Path("/tmp/view"))
    monkeypatch.setattr(loader, "_read", lambda *a, **k: table)
    frame = loader.valuation_frame("2026-10-01", "2026-10-30", ["600519.SH"])
    assert len(frame) == 2
    assert "pcf_ocf_ttm" in frame.columns
    assert loader._clean(frame.iloc[0]["float_mv"]) is None
