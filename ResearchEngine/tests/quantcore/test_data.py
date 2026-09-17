"""``DataEngine`` 与各 provider 的测试。"""

import pandas as pd
import pytest

from app.database.data.providers.field_parquet_provider import FieldParquetProvider

from app.database.data.providers.csv_provider import CSVDataProvider
from app.services.data.engine import DataEngine


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


def test_data_engine_rejects_provider_without_core_contract():
    with pytest.raises(TypeError, match="缺少方法"):
        DataEngine(object())


def test_data_engine_provider_name_and_provider_swap(tmp_path):
    provider = CSVDataProvider(tmp_path)
    engine = DataEngine(provider)

    assert engine.provider_name == "csv"
    engine.set_provider(None)
    assert engine.provider_name is None
    with pytest.raises(RuntimeError, match="尚未设置数据源"):
        engine.get_symbols()


def test_data_engine_uses_default_panel_assembly_for_duck_provider():
    dates = pd.to_datetime(["2024-01-02"])

    class _DuckProvider:
        name = "duck"

        def get_bars(self, symbol, start=None, end=None, fields=None):
            return pd.DataFrame({"close": [10.0]}, index=dates)

        def get_universe(self, date=None):
            return ["A"]

        def get_symbols(self):
            return ["A"]

    panels = DataEngine(_DuckProvider()).get_panels(fields=["close"])
    assert panels["close"].loc[dates[0], "A"] == 10.0


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


def test_field_parquet_provider_reads_ifind_marketdata_layout(tmp_path):
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    symbols = ["000001.SZ", "600000.SH"]
    (tmp_path / "data_manifest.yaml").write_text(
        "data_version: test-ifind-release\n", encoding="utf-8"
    )

    market_dir = tmp_path / "market_data"
    market_dir.mkdir()
    market_fields = ["open", "high", "low", "close", "volume"]
    market_columns = pd.MultiIndex.from_product([symbols, market_fields])
    market = pd.DataFrame(
        [
            [10.0, 11.0, 9.0, 10.5, 100.0, 20.0, 21.0, 19.0, 20.5, 200.0],
            [11.0, 12.0, 10.0, 11.5, 110.0, 21.0, 22.0, 20.0, 21.5, 210.0],
        ],
        index=dates,
        columns=market_columns,
    )
    market.index.name = "date"
    market.to_parquet(market_dir / "market_data_hfq.parquet")

    date_sequence_dir = tmp_path / "date_sequence"
    date_sequence_dir.mkdir()
    date_sequence = pd.DataFrame(
        [
            [1.2, 100.0, "非涨跌停", "在市", 2.0, 200.0, "非涨跌停", "在市"],
            [1.3, 101.0, "涨停", "暂停上市", 2.1, 201.0, "停牌", "在市"],
        ],
        index=dates,
        columns=pd.MultiIndex.from_product(
            [
                symbols,
                [
                    "ths_pb_mrq_stock",
                    "ths_current_mv_stock",
                    "ths_up_and_down_status_stock",
                    "ths_listed_status_stock",
                ],
            ]
        ),
    )
    date_sequence.index.name = "date"
    date_sequence.to_parquet(date_sequence_dir / "date_sequence.parquet")

    index_price_dir = tmp_path / "index" / "index_price"
    index_price_dir.mkdir(parents=True)
    pd.DataFrame(
        {"open": [100.0, 101.0], "high": [102.0, 103.0], "low": [99.0, 100.0], "close": [101.0, 102.0]},
        index=dates,
    ).to_parquet(index_price_dir / "index_price_000300.SH.parquet")
    index_weights_dir = tmp_path / "index" / "index_weights"
    index_weights_dir.mkdir(parents=True)
    pd.DataFrame(
        {"000001.SZ": [0.6, float("nan")], "600000.SH": [0.4, 1.0]},
        index=dates,
    ).to_parquet(index_weights_dir / "index_weights_000300.SH.parquet")

    universe_dir = tmp_path / "universe"
    universe_dir.mkdir()
    pd.DataFrame(
        {"thscode": symbols, "name": ["平安银行", "浦发银行"]}
    ).to_parquet(universe_dir / "a_share.parquet", index=False)

    provider = FieldParquetProvider(tmp_path)
    panels = provider.get_panels(
        fields=["close", "pb_mrq", "up_and_down_status", "listed_status"]
    )

    with pytest.raises(KeyError, match="pb"):
        provider.get_panels(fields=["pb"])

    assert provider.data_version == "test-ifind-release"
    assert panels["close"].loc[dates[1], "600000"] == 21.5
    assert panels["pb_mrq"].loc[dates[0], "000001"] == 1.2
    assert panels["up_and_down_status"].loc[dates[0], "600000"] == "非涨跌停"
    assert panels["listed_status"].loc[dates[1], "000001"] == "暂停上市"
    assert panels["up_and_down_status"].loc[dates[1], "600000"] == "停牌"
    assert provider.get_bars("600000.SH", fields=["close", "pb_mrq"]).iloc[0].to_dict() == {
        "close": 20.5,
        "pb_mrq": 2.0,
    }
    assert provider.get_symbols() == ["000001", "600000"]
    assert provider.get_universe("CSI300") == ["600000"]
    assert list(provider.get_index("CSI300").columns) == ["open", "high", "low", "close"]


def test_field_parquet_provider_caches_combined_schema(tmp_path, monkeypatch):
    columns = pd.MultiIndex.from_tuples([("000001.SZ", "close")])
    frame = pd.DataFrame(
        [[10.0]], index=pd.to_datetime(["2024-01-02"]), columns=columns
    )
    frame.index.name = "date"
    path = tmp_path / "market_data.parquet"
    frame.to_parquet(path)

    import pyarrow.parquet as pq
    from app.database.data.providers import field_parquet_provider as provider_module

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
        panels_dir / "pb_mrq.parquet", index=False
    )

    panels = FieldParquetProvider(tmp_path).get_panels(fields=["close", "pb_mrq"])
    assert list(panels["close"].columns) == ["000001"]
    assert panels["pb_mrq"].iloc[0, 0] == 2.0


def test_field_parquet_provider_reads_multiple_domain_panel_files(tmp_path):
    panels_dir = tmp_path / "current" / "panels"
    panels_dir.mkdir(parents=True)
    dates = pd.to_datetime(["2024-01-02"])
    for filename, values in (
        ("market_data.parquet", {"close": 10.0}),
        ("daily_basic.parquet", {"pb_mrq": 2.0}),
        ("security_status.parquet", {"up_and_down_status": "非涨跌停"}),
    ):
        frame = pd.DataFrame(
            [list(values.values())],
            index=dates,
            columns=pd.MultiIndex.from_tuples([("000001.SZ", field) for field in values]),
        )
        frame.index.name = "date"
        frame.to_parquet(panels_dir / filename)

    panels = FieldParquetProvider(tmp_path).get_panels(
        fields=["close", "pb_mrq", "up_and_down_status"]
    )

    assert panels["close"].iloc[0, 0] == 10.0
    assert panels["pb_mrq"].iloc[0, 0] == 2.0
    assert panels["up_and_down_status"].iloc[0, 0] == "非涨跌停"
