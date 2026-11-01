# -*- coding: utf-8 -*-
"""R03：数据底座状态。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.data import foundation  # noqa: E402


def test_reports_missing_and_ok(tmp_path, monkeypatch) -> None:
    manifest = {
        "view_id": "research-rv-test",
        "contract_version": "2026-11-01",
        "datasets": {
            "daily_bars": {"path": "ifind/market_data/market_data_hfq.parquet"},
            "valuation_daily": {"path": "derived/valuation_daily", "date_min": "2016-01-19", "date_max": "2026-10-30"},
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "ifind" / "market_data").mkdir(parents=True)
    (tmp_path / "ifind" / "market_data" / "market_data_hfq.parquet").write_bytes(b"")
    (tmp_path / "derived" / "valuation_daily").mkdir(parents=True)
    monkeypatch.setattr(foundation, "materialized_view_root", lambda: tmp_path)
    out = foundation.foundation_status()
    assert out["view_id"] == "research-rv-test"
    assert out["ok"] is False
    assert "industry_daily" in out["missing"]
    rows = {row["name"]: row for row in out["datasets"]}
    assert rows["valuation_daily"]["available"] is True
    assert rows["valuation_daily"]["coverage_start"] == "2016-01-19"


def test_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(foundation, "materialized_view_root", lambda: None)
    out = foundation.foundation_status()
    assert out["ok"] is False and out["reason"] == "view_not_configured"
