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
        "update_index_weights_csv",
        lambda root, index, as_of: calls.append(("index_csv", index, as_of)) or {"rows": 1},
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
        "update_index_price_csv",
        lambda root, index, as_of: calls.append(("index_price_csv", index, as_of)) or {"rows": 1},
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
        "update_daily_csv",
        lambda root, as_of, workers, universe: calls.append(
            ("market_csv", as_of, workers, universe)
        ) or {"rows": 1},
    )
    monkeypatch.setattr(
        everydayupdate,
        "csv_to_parquet",
        lambda source, target: calls.append(("market_parquet", source, target)) or {"rows": 1},
    )

    result = everydayupdate.run_everyday_update(
        object(), tmp_path, "2026-08-11", "000905.SH", workers=2
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
    ]
    assert calls[5] == ("index_download", "000905.SH", "2026-08-11", "2026-08-11")
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
    assert calls[11] == ("market_download", universe_path, "2026-08-11", "2026-08-11", 1)
    assert calls[13] == (
        "market_parquet",
        tmp_path / "market_data" / "market_data_hfq.csv",
        tmp_path / "market_data" / "market_data_hfq.parquet",
    )
    assert result["as_of"] == "2026-08-11"
    assert result["reference_data"]["index"]["code"] == "000905.SH"
    assert result["reference_data"]["index"]["price"]["parquet"] == {"rows": 1}
    assert result["market_data"]["adjustment"] == "hfq"
