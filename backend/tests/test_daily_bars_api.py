# -*- coding: utf-8 -*-
"""R06 / FEAT-015：个股日线 API（OHLCV + 换手率口径）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.data import marketdata_store as md  # noqa: E402


def test_hfq_turnover_decimal_is_converted_to_percent(monkeypatch) -> None:
    monkeypatch.setattr(
        md,
        "_daily_panel",
        lambda *a, **k: {
            "items": [{"date": "2026-10-30", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10, "amount": 20, "turnover": 0.00479387}],
            "count": 1,
            "data_version": "v-test",
        },
    )
    out = md.daily_bars("600519", adjusted=True)
    assert out["adjust"] == "hfq"
    assert out["turnover_unit"] == "percent"
    assert out["items"][0]["turnover"] == pytest.approx(0.479387, rel=1e-6)
    assert set(out["items"][0]) >= {"open", "high", "low", "close", "volume", "amount", "turnover"}


def test_unadjusted_uses_derived_long_table(monkeypatch) -> None:
    monkeypatch.setattr(
        md,
        "_long_panel",
        lambda *a, **k: [
            {"date": "2026-10-30", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10, "amount": 20, "turnover": 0.48}
        ],
    )
    out = md.daily_bars("600519.SH", adjusted=False)
    assert out["adjust"] == "none"
    assert out["items"][0]["turnover"] == 0.48
    assert out["count"] == 1


def test_limit_keeps_tail(monkeypatch) -> None:
    rows = [{"date": f"2026-10-0{i}", "close": i} for i in range(1, 6)]
    monkeypatch.setattr(md, "_daily_panel", lambda *a, **k: {"items": rows, "count": 5})
    out = md.daily_bars("600519", limit=2)
    assert [r["date"] for r in out["items"]] == ["2026-10-04", "2026-10-05"]
    assert out["count"] == 2


def test_symbol_normalization_rejects_bad_code() -> None:
    with pytest.raises(ValueError):
        md.daily_bars("NOT-A-CODE")
