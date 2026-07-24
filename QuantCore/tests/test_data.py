"""``DataEngine`` 与各 provider 的测试。"""

import pandas as pd

from quantcore.data.providers.field_parquet_provider import FieldParquetProvider

from quantcore import CSVDataProvider, DataEngine


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
        {"000001.SZ": [1, 0], "000002.SZ": [0, 1], "000003.SZ": [0, 1]},
        index=pd.to_datetime(["2024-01-01", "2024-06-01"]),
    ).to_parquet(benchmark / "CSI500_constituents.parquet")

    provider = FieldParquetProvider(tmp_path)
    assert provider.get_universe("CSI500") == ["000002", "000003"]


def test_field_parquet_provider_resolves_market_data_current_directory(tmp_path):
    panels = tmp_path / "current" / "panels"
    panels.mkdir(parents=True)
    pd.DataFrame({
        "datetime": pd.to_datetime(["2024-01-02"]), "000001": [10.0],
    }).to_parquet(panels / "close.parquet", index=False)
    benchmark = tmp_path / "current" / "benchmark"
    benchmark.mkdir()
    pd.DataFrame({"000001.SZ": [1]}).to_parquet(
        benchmark / "CSI500_constituents.parquet"
    )

    provider = FieldParquetProvider(tmp_path)
    assert provider.get_panels(fields=["close"])["close"].iloc[0, 0] == 10.0
    assert provider.get_universe("CSI500") == ["000001"]


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
