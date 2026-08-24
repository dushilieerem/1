"""``DataEngine`` 与各 provider 的测试。"""

import pandas as pd
import pytest

from app.quantcore.data.providers.field_parquet_provider import FieldParquetProvider

from app.quantcore import CSVDataProvider, DataEngine


def _write_csv(path, symbol, rows):
    df = pd.DataFrame(rows)
    df.to_csv(path / f"{symbol}.csv", index=False)


def test_csv_provider_get_bars(tmp_path):
    _write_csv(tmp_path, "600000", [
        {"date": "2022-01-04", "open": 10, "high": 11, "low": 9.5, "close": 10.5, "volume": 1000},
        {"date": "2022-01-05", "open": 10.5, "high": 10.8, "low": 10.2, "close": 10.6, "volume": 1200},
        {"date": "2022-01-06", "open": 10.6, "high": 11.0, "low": 10.4, "close": 10.9, "volume": 900},
    ])
    provider = CSVDataProvider(tmp_path)
    bars = provider.get_bars("600000")
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
    assert len(bars) == 3
    assert bars.index[0] == pd.Timestamp("2022-01-04")


def test_csv_provider_date_and_field_filter(tmp_path):
    _write_csv(tmp_path, "600000", [
        {"date": "2022-01-04", "open": 10, "high": 11, "low": 9.5, "close": 10.5, "volume": 1000},
        {"date": "2022-01-05", "open": 10.5, "high": 10.8, "low": 10.2, "close": 10.6, "volume": 1200},
        {"date": "2022-01-06", "open": 10.6, "high": 11.0, "low": 10.4, "close": 10.9, "volume": 900},
    ])
    provider = CSVDataProvider(tmp_path)
    bars = provider.get_bars("600000", start="2022-01-05", end="2022-01-05", fields=["close"])
    assert len(bars) == 1
    assert list(bars.columns) == ["close"]
    assert bars["close"].iloc[0] == 10.6


def test_data_engine_universe_pool(tmp_path):
    _write_csv(tmp_path, "600001", [{"date": "2022-01-04", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    _write_csv(tmp_path, "600002", [{"date": "2022-01-04", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    pd.DataFrame({"pool": ["CSI500"], "symbols": ["600001;600002"]}).to_csv(
        tmp_path / "universe.csv", index=False
    )
    engine = DataEngine(CSVDataProvider(tmp_path))
    assert set(engine.get_universe("CSI500")) == {"600001", "600002"}
    assert set(engine.get_symbols()) == {"600001", "600002"}


def test_field_parquet_provider_uses_latest_index_constituents(tmp_path):
    pd.DataFrame({
        "datetime": pd.to_datetime(["2024-01-02"]),
        "000001": [10.0], "000002": [20.0], "000003": [30.0],
    }).to_parquet(tmp_path / "close.parquet", index=False)
    benchmark = tmp_path / "benchmark"
    benchmark.mkdir()
    pd.DataFrame(
        {"000001.SZ": [0.6, float("nan")], "000002.SZ": [0.4, 0.55], "000003.SZ": [float("nan"), 0.45]},
        index=pd.to_datetime(["2024-01-01", "2024-06-01"]),
    ).to_parquet(benchmark / "index_weights_000905.SH.parquet")

    provider = FieldParquetProvider(tmp_path)
    assert provider.get_universe("CSI500") == ["000002", "000003"]


def test_field_parquet_provider_uses_point_in_time_index_constituents(tmp_path):
    pd.DataFrame({
        "datetime": pd.to_datetime(["2024-01-02", "2024-01-03"]),
        "000001": [10.0, 10.1],
        "000002": [20.0, 20.1],
        "000003": [30.0, 30.1],
    }).to_parquet(tmp_path / "close.parquet", index=False)
    benchmark = tmp_path / "benchmark"
    benchmark.mkdir()
    pd.DataFrame(
        {
            "000001.SZ": [0.6, float("nan")],
            "000002.SZ": [0.4, 0.5],
            "000003.SZ": [float("nan"), 0.5],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    ).to_parquet(benchmark / "index_weights_000905.SH.parquet")

    provider = FieldParquetProvider(tmp_path)

    assert provider.get_universe_at("CSI500", "2024-01-02") == ["000001", "000002"]
    assert provider.get_universe_at("CSI500", "2024-01-03") == ["000002", "000003"]


def test_field_parquet_provider_never_uses_future_universe_snapshot(tmp_path):
    pd.DataFrame({
        "datetime": pd.to_datetime(["2024-01-02"]), "000001": [10.0],
    }).to_parquet(tmp_path / "close.parquet", index=False)
    benchmark = tmp_path / "benchmark"
    benchmark.mkdir()
    pd.DataFrame(
        {"000001.SZ": [1.0]}, index=pd.to_datetime(["2024-01-03"])
    ).to_parquet(benchmark / "index_weights_000905.SH.parquet")

    provider = FieldParquetProvider(tmp_path)

    with pytest.raises(ValueError, match="没有可用快照"):
        provider.get_universe_at("CSI500", "2024-01-02")


def test_field_parquet_provider_resolves_market_data_current_directory(tmp_path):
    panels = tmp_path / "current" / "panels"
    panels.mkdir(parents=True)
    pd.DataFrame({
        "datetime": pd.to_datetime(["2024-01-02"]), "000001": [10.0],
    }).to_parquet(panels / "close.parquet", index=False)
    benchmark = tmp_path / "current" / "benchmark"
    benchmark.mkdir()
    pd.DataFrame({"000001.SZ": [100.0]}).to_parquet(
        benchmark / "index_weights_000905.SH.parquet"
    )

    provider = FieldParquetProvider(tmp_path)
    assert provider.get_panels(fields=["close"])["close"].iloc[0, 0] == 10.0
    assert provider.get_universe("CSI500") == ["000001"]


def test_field_parquet_provider_reads_all_a_static_universe(tmp_path):
    pd.DataFrame({
        "datetime": pd.to_datetime(["2024-01-02"]), "000001": [10.0], "600000": [20.0],
    }).to_parquet(tmp_path / "close.parquet", index=False)
    universe = tmp_path / "universe"
    universe.mkdir()
    pd.DataFrame({"thscode": ["000001.SZ", "600000.SH"], "name": ["平安银行", "浦发银行"]}).to_parquet(
        universe / "a_share.parquet", index=False
    )

    provider = FieldParquetProvider(tmp_path)

    assert provider.get_universe("CSI_ALL") == ["000001", "600000"]
    assert provider.get_symbols() == ["000001", "600000"]


def test_field_parquet_provider_reads_legacy_pandas_datetime_index(tmp_path):
    frame = pd.DataFrame(
        {"000001": [10.0, 11.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    frame.index.name = "datetime"
    frame.to_parquet(tmp_path / "close.parquet")

    panel = FieldParquetProvider(tmp_path).get_panels(fields=["close"])["close"]
    assert panel.index.name == "datetime"
    assert panel.index.tolist() == frame.index.tolist()
    assert panel.loc[pd.Timestamp("2024-01-03"), "000001"] == 11.0


def test_field_parquet_provider_reads_ifind_combined_market_data(tmp_path):
    columns = pd.MultiIndex.from_product(
        [["000001.SZ", "600000.SH"], ["open", "high", "low", "close", "volume", "amount", "turnover"]]
    )
    frame = pd.DataFrame(
        [[row * 14 + column for column in range(14)] for row in range(2)],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
        columns=columns,
    )
    frame.index.name = "date"
    path = tmp_path / "market_data.parquet"
    frame.to_parquet(path)

    provider = FieldParquetProvider(path)
    panels = provider.get_panels(fields=["open", "close", "turnover"])

    assert provider.get_symbols() == ["000001", "600000"]
    assert panels["close"].index.name == "datetime"
    assert list(panels["close"].columns) == ["000001", "600000"]
    assert panels["turnover"].loc[pd.Timestamp("2024-01-03"), "600000"] == 27
    assert list(provider.get_bars("000001.SZ", fields=["open", "close"]).columns) == ["open", "close"]
    assert provider.get_bars("000001", fields=["close"]).iloc[0, 0] == 3


def test_field_parquet_provider_caches_combined_schema(tmp_path, monkeypatch):
    columns = pd.MultiIndex.from_tuples([("000001.SZ", "close")])
    frame = pd.DataFrame(
        [[10.0]], index=pd.to_datetime(["2024-01-02"]), columns=columns
    )
    frame.index.name = "date"
    path = tmp_path / "market_data.parquet"
    frame.to_parquet(path)

    import pyarrow.parquet as pq
    from app.quantcore.data.providers import field_parquet_provider as provider_module

    provider_module._SCHEMA_CACHE.pop(path.resolve(), None)
    calls = []
    original = pq.read_schema

    def counted_read_schema(schema_path, *args, **kwargs):
        calls.append(schema_path)
        return original(schema_path, *args, **kwargs)

    monkeypatch.setattr(pq, "read_schema", counted_read_schema)
    FieldParquetProvider(path)
    FieldParquetProvider(path)

    assert len(calls) == 1


def test_field_parquet_provider_prefers_combined_market_data_in_panels_directory(tmp_path):
    panels_dir = tmp_path / "current" / "panels"
    panels_dir.mkdir(parents=True)
    columns = pd.MultiIndex.from_product([["000001.SZ"], ["open", "close"]])
    frame = pd.DataFrame([[1.0, 2.0]], index=pd.to_datetime(["2024-01-02"]), columns=columns)
    frame.index.name = "date"
    frame.to_parquet(panels_dir / "market_data.parquet")

    provider = FieldParquetProvider(tmp_path)
    assert provider.get_panels(fields=["close"])["close"].iloc[0, 0] == 2.0


def test_field_parquet_provider_keeps_non_market_fields_with_combined_file(tmp_path):
    panels_dir = tmp_path / "current" / "panels"
    panels_dir.mkdir(parents=True)
    dates = pd.to_datetime(["2024-01-02"])
    combined = pd.DataFrame(
        [[10.0]], index=dates, columns=pd.MultiIndex.from_tuples([("000001.SZ", "close")])
    )
    combined.index.name = "date"
    combined.to_parquet(panels_dir / "market_data.parquet")
    pd.DataFrame({"datetime": dates, "000001": [2.0]}).to_parquet(
        panels_dir / "pb.parquet", index=False
    )

    panels = FieldParquetProvider(tmp_path).get_panels(fields=["close", "pb"])
    assert list(panels["close"].columns) == ["000001"]
    assert panels["pb"].iloc[0, 0] == 2.0


def test_field_parquet_provider_reads_multiple_domain_panel_files(tmp_path):
    panels_dir = tmp_path / "current" / "panels"
    panels_dir.mkdir(parents=True)
    dates = pd.to_datetime(["2024-01-02"])
    for filename, values in (
        ("market_data.parquet", {"close": 10.0}),
        ("daily_basic.parquet", {"pb": 2.0}),
        ("security_status.parquet", {"is_suspended": False}),
    ):
        frame = pd.DataFrame(
            [list(values.values())],
            index=dates,
            columns=pd.MultiIndex.from_tuples([("000001.SZ", field) for field in values]),
        )
        frame.index.name = "date"
        frame.to_parquet(panels_dir / filename)

    panels = FieldParquetProvider(tmp_path).get_panels(fields=["close", "pb", "is_suspended"])

    assert panels["close"].iloc[0, 0] == 10.0
    assert panels["pb"].iloc[0, 0] == 2.0
    assert not panels["is_suspended"].iloc[0, 0]
