# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from services.data.view_sync import (
    ViewInfo,
    _clean,
    _dataset_files,
    _is_safe_db,
    plan_sync,
    resolve_view,
    validate_view,
)


def _manifest(view_id: str = "view-test", data_date: str = "2026-11-02", contract: str = "2026-11-01"):
    datasets = {
        name: {"path": f"derived/{name}", "date_max": data_date}
        for name in (
            "daily_bars",
            "daily_bars_unadjusted",
            "valuation_daily",
            "security_status_daily",
            "limit_prices",
            "index_price",
            "security_master",
            "calendar",
            "industry_code_map",
        )
    }
    return {
        "view_id": view_id,
        "contract_version": contract,
        "datasets": datasets,
    }


def test_resolve_current_symlink(tmp_path: Path):
    root = tmp_path / "data"
    base = root / "views" / "view-test"
    materialized = base / "materialized"
    materialized.mkdir(parents=True)
    (materialized / "manifest.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    (root / "views" / "current").symlink_to(materialized)

    view = resolve_view(root, "current")
    assert view.view_id == "view-test"
    assert view.root == materialized.resolve()
    assert view.data_date == date(2026, 11, 2)


def test_validate_rejects_contract_mismatch(tmp_path: Path):
    view = ViewInfo("v", tmp_path, _manifest(contract="2026-10-01"), "2026-10-01", date(2026, 11, 2))
    with pytest.raises(ValueError, match="contract"):
        validate_view(view, expected_contract="2026-11-01")


def test_validate_rejects_missing_dataset(tmp_path: Path):
    manifest = _manifest()
    manifest["datasets"].pop("limit_prices")
    view = ViewInfo("v", tmp_path, manifest, "2026-11-01", date(2026, 11, 2))
    with pytest.raises(ValueError, match="limit_prices"):
        validate_view(view)


def test_plan_unchanged(tmp_path: Path):
    view = ViewInfo("v", tmp_path, _manifest(), "2026-11-01", date(2026, 11, 2))
    out = plan_sync(view, {"view_id": "v", "data_date": date(2026, 11, 2)})
    assert out["status"] == "unchanged"


def test_plan_incremental_from_min_state_and_db(tmp_path: Path):
    view = ViewInfo("v2", tmp_path, _manifest(), "2026-11-01", date(2026, 11, 2))
    out = plan_sync(
        view,
        {"view_id": "v1", "data_date": date(2026, 11, 2)},
        max_db_date=date(2026, 10, 30),
    )
    assert out["status"] == "sync"
    assert out["start"] == "2026-10-31"
    assert out["end"] == "2026-11-02"


def test_plan_fresh_when_start_after_end(tmp_path: Path):
    view = ViewInfo("v", tmp_path, _manifest(), "2026-11-01", date(2026, 11, 2))
    out = plan_sync(view, None, max_db_date=date(2026, 11, 2))
    assert out["status"] == "fresh"


def test_year_partition_filter(tmp_path: Path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    root = tmp_path / "view" / "materialized"
    base = root / "derived" / "daily_bars_unadjusted"
    for year in (2025, 2026):
        path = base / f"year={year}" / "part.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table({"date": ["2025-01-01"]}), path)

    view = ViewInfo("v", root, _manifest(), "2026-11-01", date(2026, 11, 2))
    files = _dataset_files(view, "daily_bars_unadjusted", date(2026, 1, 1), date(2026, 12, 31))
    assert len(files) == 1
    assert "year=2026" in str(files[0])


def test_db_name_guard():
    assert _is_safe_db("svquant_dev")
    assert _is_safe_db("svquant_test")
    assert _is_safe_db("inst_e2e_20261103")
    assert not _is_safe_db("svquant")


def test_clean_bool_and_nan():
    assert _clean(True) == "true"
    assert _clean(False) == "false"
    assert _clean(float("nan")) is None
    assert _clean(None) is None
