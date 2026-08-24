from pathlib import Path
import sys

import pandas as pd
import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.akshare.update_float_mv import (  # noqa: E402
    VALUATION_FIELDS,
    consolidate_wide,
    load_universe_mapping,
    normalize_valuation,
    run,
    symbol_to_code,
)


def _raw_valuation(code: str = "000001") -> pd.DataFrame:
    base = 100.0 if code == "000001" else 200.0
    return pd.DataFrame(
        {
            "数据日期": ["2026-01-05", "2026-01-06"],
            "总市值": [base * 10, base * 11],
            "流通市值": [base * 8, base * 9],
            "总股本": [1000, 1100],
            "流通股本": [800, 900],
            "PE(TTM)": [12.0, -3.0],
            "PE(静)": [13.0, 14.0],
            "市净率": [1.2, 1.3],
            "PEG值": [0.8, 0.9],
            "市现率": [8.0, 8.5],
            "市销率": [2.0, 2.1],
        }
    )


def test_symbol_to_code_and_normalize_all_stock_value_fields():
    assert symbol_to_code("000001.SZ") == "000001"
    assert symbol_to_code("920001.BJ") == "920001"

    normalized = normalize_valuation(
        _raw_valuation(), "000001.SZ", "2026-01-05", "2026-01-06"
    )

    assert normalized["date"].tolist() == [
        pd.Timestamp("2026-01-05"),
        pd.Timestamp("2026-01-06"),
    ]
    assert normalized["symbol"].unique().tolist() == ["000001.SZ"]
    assert list(normalized.columns) == ["date", "symbol", *VALUATION_FIELDS]
    assert normalized.loc[0, "total_market_cap"] == 1000.0
    assert normalized.loc[1, "notlimited_marketcap_a"] == 900.0
    assert normalized.loc[1, "pe_ttm"] == -3.0


def test_load_universe_mapping_rejects_duplicate_codes(tmp_path):
    path = tmp_path / "a_share.parquet"
    pd.DataFrame({"thscode": ["000001.SZ", "000001.SH"]}).to_parquet(
        path, index=False
    )

    with pytest.raises(ValueError, match="重复六位代码"):
        load_universe_mapping(path)


def test_consolidate_wide_reads_one_symbol_file_at_a_time(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    symbols = ("000001.SZ", "000002.SZ")
    for symbol in symbols:
        code = symbol.split(".")[0]
        frame = _raw_valuation(code)
        frame.insert(1, "symbol", symbol)
        frame.rename(columns={"数据日期": "date"}, inplace=True)
        frame = frame.rename(
            columns={
                "总市值": "total_market_cap",
                "流通市值": "notlimited_marketcap_a",
                "总股本": "total_shares",
                "流通股本": "free_shares_a",
                "PE(TTM)": "pe_ttm",
                "PE(静)": "pe_lar",
                "市净率": "pb_mrq",
                "PEG值": "peg_car",
                "市现率": "pcf_ocf_ttm",
                "市销率": "ps_ttm",
            }
        )
        frame.to_parquet(
            cache_dir / f"{symbol.replace('.', '_')}.parquet", index=False
        )

    output = tmp_path / "daily_basic.parquet"
    report = consolidate_wide(
        symbols,
        {
            symbol: cache_dir / f"{symbol.replace('.', '_')}.parquet"
            for symbol in symbols
        },
        output,
        chunk_size=1,
    )
    panel = pd.read_parquet(output)

    assert report["rows"] == 2
    assert report["fields"] == list(VALUATION_FIELDS)
    assert panel.shape == (2, len(symbols) * len(VALUATION_FIELDS))
    assert panel.columns.names == ["symbol", "field"]
    assert panel.loc[pd.Timestamp("2026-01-05"), ("000001.SZ", "total_market_cap")] == 1000.0
    assert panel.loc[pd.Timestamp("2026-01-06"), ("000002.SZ", "free_shares_a")] == 900.0


def test_run_uses_bare_code_and_writes_historical_panel(tmp_path):
    universe_path = tmp_path / "a_share.parquet"
    pd.DataFrame({"thscode": ["000001.SZ", "000002.SZ"]}).to_parquet(
        universe_path, index=False
    )
    fetched: list[str] = []

    def fake_fetcher(code):
        fetched.append(code)
        return _raw_valuation(code)

    output = tmp_path / "daily_basic_history.parquet"
    report = run(
        start_date="2026-01-05",
        end_date="2026-01-06",
        universe_path=universe_path,
        cache_dir=tmp_path / "cache",
        output_path=output,
        throttle_seconds=0,
        retry_delay=0,
        fetcher=fake_fetcher,
    )
    panel = pd.read_parquet(output)

    assert fetched == ["000001", "000002"]
    assert report["source"] == "akshare.stock_value_em"
    assert report["source_fields"]["total_market_cap"] == "TOTAL_MARKET_CAP"
    assert report["source_fields"]["pcf_ocf_ttm"] == "PCF_OCF_TTM"
    assert report["completed_symbols"] == 2
    assert report["failed_symbols"] == 0
    assert panel.shape == (2, 2 * len(VALUATION_FIELDS))
    assert panel.loc[pd.Timestamp("2026-01-05"), ("000001.SZ", "pe_ttm")] == 12.0
    assert panel.loc[pd.Timestamp("2026-01-06"), ("000002.SZ", "total_market_cap")] == 2200.0
