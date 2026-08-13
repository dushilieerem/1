from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.ifind import everydayupdate  # noqa: E402


def test_everyday_update_runs_all_stages_in_dependency_order(tmp_path, monkeypatch):
    calls: list[tuple] = []
    universe_path = tmp_path / "universe" / "a_share.csv"

    monkeypatch.setattr(
        everydayupdate,
        "update_calendar",
        lambda client, root, as_of: calls.append(("calendar", root, as_of)) or 1,
    )
    monkeypatch.setattr(
        everydayupdate,
        "read_calendar_dates",
        lambda path: ["2026-08-08", "2026-08-11"],
    )
    monkeypatch.setattr(
        everydayupdate,
        "_latest_csv_date",
        lambda path: {
            "index_weights_000905.SH.csv": "2026-08-07",
            "index_price_000905.SH.csv": "2026-08-08",
            "market_data_hfq.csv": "2026-08-07",
            "unadjusted_price.csv": "2026-08-08",
        }.get(path.name),
    )
    monkeypatch.setattr(
        everydayupdate,
        "csv_to_flat_parquet",
        lambda source, target, label: calls.append((label, source, target)) or {"rows": 1},
    )
    monkeypatch.setattr(
        everydayupdate,
        "run_universe_download",
        lambda client, root, as_of: calls.append(("universe_download", root, as_of)) or {"downloaded": 3},
    )
    monkeypatch.setattr(
        everydayupdate,
        "update_universe_csv",
        lambda root, as_of: calls.append(("universe_csv", root, as_of)) or {"rows": 3},
    )
    monkeypatch.setattr(everydayupdate, "existing_universe_path", lambda root: universe_path)
    monkeypatch.setattr(
        everydayupdate,
        "download_index_weights",
        lambda client, root, index, start, end: calls.append(("index_download", index, start, end)) or {"raw_partitions": 1},
    )
    monkeypatch.setattr(
        everydayupdate,
        "update_index_weights_csv_range",
        lambda root, index, dates: calls.append(("index_csv", index, dates)) or {"rows": 2},
    )
    monkeypatch.setattr(
        everydayupdate,
        "csv_to_index_weights_parquet",
        lambda source, target: calls.append(("index_parquet", source, target)) or {"rows": 1},
    )
    monkeypatch.setattr(
        everydayupdate,
        "download_index_price",
        lambda client, root, index, start, end, days, points: calls.append(
            ("index_price_download", index, start, end, days)
        ) or {"raw_partitions": 1},
    )
    monkeypatch.setattr(
        everydayupdate,
        "update_index_price_csv_range",
        lambda root, index, dates: calls.append(("index_price_csv", index, dates)) or {"rows": 1},
    )
    monkeypatch.setattr(
        everydayupdate,
        "csv_to_index_price_parquet",
        lambda source, target: calls.append(("index_price_parquet", source, target)) or {"rows": 1},
    )
    monkeypatch.setattr(
        everydayupdate,
        "download_market_data",
        lambda client, root, universe, start, end, symbols, days, points: calls.append(
            ("market_download", universe, start, end, days)
        ) or {"price_hfq": {"raw_partitions": 1}},
    )
    monkeypatch.setattr(
        everydayupdate,
        "update_daily_csv_range",
        lambda root, dates, workers, universe: calls.append(
            ("market_csv", dates, workers, universe)
        ) or {"rows": 2},
    )
    monkeypatch.setattr(
        everydayupdate,
        "csv_to_parquet",
        lambda source, target: calls.append(("market_parquet", source, target)) or {"rows": 1},
    )
    monkeypatch.setattr(
        everydayupdate,
        "download_unadjusted_price",
        lambda client, root, universe, start, end, symbols, days, points: calls.append(
            ("unadjusted_download", universe, start, end, days)
        ) or {"price_none": {"raw_partitions": 1}},
    )
    monkeypatch.setattr(
        everydayupdate,
        "update_price_csv_range",
        lambda root, dates, workers, universe: calls.append(
            ("unadjusted_csv", dates, workers, universe)
        ) or {"rows": 1},
    )
    monkeypatch.setattr(
        everydayupdate,
        "csv_to_unadjusted_price_parquet",
        lambda source, target: calls.append(
            ("unadjusted_parquet", source, target)
        ) or {"rows": 1},
    )

    result = everydayupdate.run_everyday_update(
        object(), tmp_path, "2026-08-11", ["000905.SH"], workers=2
    )

    assert [call[0] for call in calls] == [
        "calendar",
        "calendar_parquet",
        "universe_download",
        "universe_csv",
        "universe_parquet",
        "index_download",
        "index_csv",
        "index_parquet",
        "index_price_download",
        "index_price_csv",
        "index_price_parquet",
        "market_download",
        "market_csv",
        "market_parquet",
        "unadjusted_download",
        "unadjusted_csv",
        "unadjusted_parquet",
    ]
    assert calls[5] == ("index_download", "000905.SH", "2026-08-08", "2026-08-11")
    assert calls[6] == (
        "index_csv",
        "000905.SH",
        ["2026-08-08", "2026-08-11"],
    )
    assert calls[7] == (
        "index_parquet",
        tmp_path / "index" / "index_weights" / "index_weights_000905.SH.csv",
        tmp_path / "index" / "index_weights" / "index_weights_000905.SH.parquet",
    )
    assert calls[8] == ("index_price_download", "000905.SH", "2026-08-11", "2026-08-11", 1)
    assert calls[10] == (
        "index_price_parquet",
        tmp_path / "index" / "index_price" / "index_price_000905.SH.csv",
        tmp_path / "index" / "index_price" / "index_price_000905.SH.parquet",
    )
    assert calls[11] == ("market_download", universe_path, "2026-08-08", "2026-08-11", 1)
    assert calls[12] == (
        "market_csv",
        ["2026-08-08", "2026-08-11"],
        2,
        universe_path,
    )
    assert calls[13] == (
        "market_parquet",
        tmp_path / "market_data" / "market_data_hfq.csv",
        tmp_path / "market_data" / "market_data_hfq.parquet",
    )
    assert calls[14] == (
        "unadjusted_download",
        universe_path,
        "2026-08-11",
        "2026-08-11",
        1,
    )
    assert calls[15] == (
        "unadjusted_csv",
        ["2026-08-11"],
        2,
        universe_path,
    )
    assert result["as_of"] == "2026-08-11"
    assert result["reference_data"]["indices"]["000905.SH"]["price"]["parquet"] == {"rows": 1}
    assert result["reference_data"]["indices"]["000905.SH"]["weights"]["update_range"] == {
        "count": 2,
        "start": "2026-08-08",
        "end": "2026-08-11",
    }
    assert result["market_data"]["adjustment"] == "hfq"
    assert result["unadjusted_price"]["adjustment"] == "none"
    assert result["unadjusted_price"]["update_range"] == {
        "count": 1,
        "start": "2026-08-11",
        "end": "2026-08-11",
    }


def test_latest_csv_date_reads_last_wide_row_without_scanning_from_start(tmp_path):
    path = tmp_path / "wide.csv"
    path.write_text(
        "date,symbol\n"
        "2026-08-08,1\n"
        f"2026-08-11,{'1' * 100_000}\n",
        encoding="utf-8",
    )

    assert everydayupdate._latest_csv_date(path) == "2026-08-11"


def test_missing_trade_dates_starts_after_each_assets_own_maximum(tmp_path):
    path = tmp_path / "asset.csv"
    path.write_text("date,value\n2026-08-08,1\n", encoding="utf-8")

    assert everydayupdate._missing_trade_dates(
        path,
        ["2026-08-08", "2026-08-11", "2026-08-12"],
    ) == ["2026-08-11", "2026-08-12"]


def test_index_list_contains_both_current_indices_and_rejects_duplicates():
    assert everydayupdate.INDEX_CODES == ["000300.SH", "000905.SH"]
    assert everydayupdate._normalize_index_codes(["000300.sh", " 000905.SH "]) == [
        "000300.SH",
        "000905.SH",
    ]

    try:
        everydayupdate._normalize_index_codes(["000300.SH", "000300.SH"])
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("重复指数代码必须被拒绝")


def test_everyday_update_uses_all_configured_indices_by_default(tmp_path, monkeypatch):
    updated_indices: list[str] = []
    universe_path = tmp_path / "universe" / "a_share.csv"
    monkeypatch.setattr(everydayupdate, "update_calendar", lambda *args: 0)
    monkeypatch.setattr(
        everydayupdate, "read_calendar_dates", lambda path: ["2026-08-11"]
    )
    monkeypatch.setattr(everydayupdate, "csv_to_flat_parquet", lambda *args: {})
    monkeypatch.setattr(everydayupdate, "run_universe_download", lambda *args, **kwargs: {})
    monkeypatch.setattr(everydayupdate, "update_universe_csv", lambda *args: {})
    monkeypatch.setattr(everydayupdate, "existing_universe_path", lambda root: universe_path)
    monkeypatch.setattr(
        everydayupdate,
        "_update_index",
        lambda client, root, index_code, dates: updated_indices.append(index_code) or {},
    )
    monkeypatch.setattr(everydayupdate, "_missing_trade_dates", lambda *args: [])
    monkeypatch.setattr(everydayupdate, "update_daily_csv_range", lambda *args: {})
    monkeypatch.setattr(everydayupdate, "csv_to_parquet", lambda *args: {})
    monkeypatch.setattr(everydayupdate, "update_price_csv_range", lambda *args: {})
    monkeypatch.setattr(
        everydayupdate, "csv_to_unadjusted_price_parquet", lambda *args: {}
    )

    result = everydayupdate.run_everyday_update(
        object(), tmp_path, "2026-08-11", workers=1
    )

    assert updated_indices == everydayupdate.INDEX_CODES
    assert list(result["reference_data"]["indices"]) == everydayupdate.INDEX_CODES
