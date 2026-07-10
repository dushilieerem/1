"""``DataEngine`` 与各 provider 的测试。"""

import pandas as pd

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
