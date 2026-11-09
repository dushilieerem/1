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
    _prune_us_snapshot,
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


def test_plan_sync_meta_when_new_view_same_date(tmp_path: Path):
    view = ViewInfo("v2", tmp_path, _manifest(), "2026-11-01", date(2026, 11, 2))
    out = plan_sync(
        view,
        {"view_id": "v1", "data_date": date(2026, 11, 2)},
        max_db_date=date(2026, 11, 2),
    )
    assert out["status"] == "sync_meta"
    assert out["start"] == "2026-11-02"


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


class _SnapshotConn:
    def __init__(self, count: int):
        self.count = count
        self.sql: list[str] = []

    def execute(self, sql, *args):
        self.sql.append(sql)
        return self

    def fetchone(self):
        return {"n": self.count}


def test_prune_us_snapshot_only_when_source_non_empty():
    empty = _SnapshotConn(0)
    assert _prune_us_snapshot(empty) == 0
    assert not any("DELETE FROM md_us_stock_snapshot" in s for s in empty.sql)

    full = _SnapshotConn(3)
    assert _prune_us_snapshot(full) == 3
    assert any("DELETE FROM md_us_stock_snapshot" in s for s in full.sql)
    assert any("tmp_md_us_stock_snapshot" in s for s in full.sql)


def test_sync_index_reads_volume_and_amount(tmp_path: Path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from services.data import view_sync

    base = tmp_path / "derived" / "index_price" / "year=2026"
    base.mkdir(parents=True)
    pq.write_table(
        pa.table({
            "date": ["2026-11-04"],
            "index_code": ["000001.SH"],
            "open": [3600.0], "high": [3700.0], "low": [3590.0], "close": [3686.17],
            "prev_close": [3608.10], "volume": [599394361.0], "amount": [953265155867.1],
            "source": ["eastmoney_index_kline"],
        }),
        base / "part.parquet",
    )
    view = ViewInfo("v", tmp_path, _manifest(data_date="2026-11-04"), "2026-11-01", date(2026, 11, 4))
    captured = {}

    def fake_copy(conn, table, columns, rows):
        captured["columns"] = columns
        captured["rows"] = list(rows)
        return len(captured["rows"])

    monkeypatch.setattr(view_sync, "_copy_rows", fake_copy)
    total = view_sync._sync_index(object(), view)
    assert total == 1
    assert "volume" in captured["columns"] and "amount" in captured["columns"]
    row = captured["rows"][0]
    assert row[0] == "000001.SH" and row[6] == 599394361.0 and row[7] == 953265155867.1


def test_sync_index_falls_back_when_old_view_has_no_volume_amount(tmp_path: Path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from services.data import view_sync

    base = tmp_path / "derived" / "index_price" / "year=2026"
    base.mkdir(parents=True)
    # 旧 view 没有 volume/amount 列；不能按 null 判断，必须按列是否存在回退。
    pq.write_table(
        pa.table({
            "date": ["2026-11-04"],
            "index_code": ["000300.SH"],
            "open": [4000.0], "high": [4050.0], "low": [3980.0], "close": [4008.87],
        }),
        base / "part.parquet",
    )
    view = ViewInfo("v", tmp_path, _manifest(data_date="2026-11-04"), "2026-11-01", date(2026, 11, 4))
    captured = {}

    def fake_copy(conn, table, columns, rows):
        captured["columns"] = columns
        captured["rows"] = list(rows)
        return len(captured["rows"])

    monkeypatch.setattr(view_sync, "_copy_rows", fake_copy)
    total = view_sync._sync_index(object(), view)
    assert total == 1
    assert "volume" in captured["columns"] and "amount" in captured["columns"]
    row = captured["rows"][0]
    assert row[0] == "000300.SH"
    assert row[6] is None and row[7] is None


def test_sync_fund_flow_candidate_reads_core_fields(tmp_path: Path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from services.data import view_sync

    base = tmp_path / "derived" / "fund_flow_candidate" / "year=2026"
    base.mkdir(parents=True)
    pq.write_table(
        pa.table({
            "symbol": ["600519.SH"], "trade_date": ["2026-11-05"],
            "main_net_inflow_5d": [85_550_000.0], "main_net_inflow_latest": [69_476_704.0],
            "main_net_ratio_latest": [4.86], "inflow_days_5d": [3],
            "consecutive_inflow_days": [4], "consecutive_outflow_days": [0],
            "days_available": [5], "source": ["eastmoney_stock_fundflow"],
            "observed_at": ["2026-11-05T17:15:20"],
        }),
        base / "part.parquet",
    )
    view = ViewInfo("v", tmp_path, _manifest(data_date="2026-11-05"), "2026-11-01", date(2026, 11, 5))
    captured = {}

    def fake_copy(conn, table, columns, rows):
        captured["table"] = table
        captured["columns"] = columns
        captured["rows"] = list(rows)
        return len(captured["rows"])

    assert "fund_flow_candidate" not in view.manifest["datasets"]
    view.manifest["datasets"]["fund_flow_candidate"] = {"path": "derived/fund_flow_candidate"}
    monkeypatch.setattr(view_sync, "_copy_rows", fake_copy)
    total = view_sync._sync_fund_flow_candidate(object(), view)
    assert total == 1
    assert captured["table"] == "tmp_md_fund_flow_candidate"
    assert captured["rows"][0][0] == "600519.SH"
    assert captured["rows"][0][6] == 4


def test_sync_ref_security_includes_chinext_star_and_bse(tmp_path: Path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from services.data import view_sync

    base = tmp_path / "free" / "security_master"
    base.mkdir(parents=True)
    pq.write_table(
        pa.table({
            "Symbol": ["600000.SH", "300750.SZ", "688981.SH", "920001.BJ"],
            "Name": ["浦发银行", "宁德时代", "中芯国际", "北交样本"],
            "IsQuitGP": ["0", "0", "0", "0"],
            "J_start": ["1999-11-10", "2018-06-11", "2020-07-16", "2024-01-01"],
            "HSStockKind": [1, 3, 4, 2],
        }),
        base / "security_master.parquet",
    )
    view = ViewInfo("v", tmp_path, _manifest(), "2026-11-01", date(2026, 11, 4))
    view.manifest["datasets"]["security_master"] = {"path": "free/security_master"}
    captured = {}

    def fake_copy(conn, table, columns, rows):
        captured["rows"] = list(rows)
        return len(captured["rows"])

    monkeypatch.setattr(view_sync, "_copy_rows", fake_copy)
    total = view_sync._sync_ref_security(object(), view)
    assert total == 4
    boards = {row[0]: row[4] for row in captured["rows"]}
    assert boards == {"600000.SH": "SH_MAIN", "300750.SZ": "ChiNext", "688981.SH": "STAR", "920001.BJ": "BSE"}


def test_doc_rows_handle_nan_and_content_hash():
    import pandas as pd

    from services.data import view_sync

    frame = pd.DataFrame([{
        "symbol": "600519.SH", "title": "公告标题", "url": "https://example.test/a",
        "available_time": "2026-11-06 10:00:00", "category": "业绩",
        "art_code": "A1", "source": "eastmoney",
    }])
    rows = view_sync._doc_rows(frame, "announcement", "data_platform_announcement", date(2026, 11, 6))
    assert len(rows) == 1
    assert rows[0][0] == "announcement"
    assert rows[0][6]
    raw = json.loads(rows[0][8])
    assert raw["title"] == "公告标题"
    assert "NaN" not in rows[0][8]
