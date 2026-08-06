import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.ifind.date_sequence_csv import build_date_sequence_csv
from data_ingestion.ifind.date_sequence_download import date_sequence_payload, raw_path as date_raw_path, run_download as run_date_sequence_download
from data_ingestion.ifind.market_data_csv import build_daily_csv
from data_ingestion.ifind.market_data_download import LIQUIDITY, PRICE, history_payload
from data_ingestion.ifind.market_data_parquet import csv_to_parquet


def test_download_payloads_only_describe_iFind_requests():
    assert history_payload(PRICE, ["600000.SH"], "2026-08-04", "2026-08-04")["reqBody"]["functionpara"] == {"CPS": "1"}
    assert history_payload(LIQUIDITY, ["600000.SH"], "2026-08-04", "2026-08-04")["reqBody"]["indicators"] == "volume,amt,turn"
    assert [item["indicator"] for item in date_sequence_payload(["600000.SH"], "2026-08-04", "2026-08-04")["indipara"]][:3] == ["ths_current_mv_stock", "ths_pe_stock", "ths_pb_stock"]


def test_json_to_complete_csv_to_parquet(tmp_path):
    price = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"open": [10], "high": [11], "low": [9], "close": [10.5]}}]}
    liquidity = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"volume": [100], "amt": [1000], "turn": [2]}}]}
    date_sequence = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"ths_current_mv_stock": [100], "ths_pe_stock": [10], "ths_pb_stock": [1], "ths_the_sw_industry_stock": ["银行"], "ths_the_sw_industry_code_stock": ["801780"], "ths_up_and_down_status_stock": ["正常"]}}]}
    for relative, body in (("prices/hfq/raw/SH/2026-08-04_2026-08-04/symbols_00001.json", price), ("liquidity/raw/SH/2026-08-04_2026-08-04/symbols_00001.json", liquidity), ("date_sequence/raw/SH/2026-08-04_2026-08-04/symbols_00001.json", date_sequence)):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body), encoding="utf-8")
    assert build_daily_csv(tmp_path)["rows"] == 1
    assert build_date_sequence_csv(tmp_path)["rows"] == 1
    assert csv_to_parquet(tmp_path / "daily.csv", tmp_path / "daily.parquet")["rows"] == 1
    with (tmp_path / "daily.csv").open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["turnover"] == "0.02"
    assert (tmp_path / "daily.parquet").is_file()


def test_download_reports_cached_batch_progress(tmp_path, capsys):
    calendar = tmp_path / "calendar" / "ALL_A.csv"
    universe = tmp_path / "universe.csv"
    calendar.parent.mkdir(parents=True)
    calendar.write_text("date\n2026-08-04\n", encoding="utf-8")
    universe.write_text("thscode,exchange\n600000.SH,SH\n000001.SZ,SZ\n920000.BJ,BJ\n", encoding="utf-8")
    for exchange, code in (("SH", "600000.SH"), ("SZ", "000001.SZ"), ("BJ", "920000.BJ")):
        path = date_raw_path(tmp_path, exchange, "2026-08-04", "2026-08-04", 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tables": [], "dataVol": 0}), encoding="utf-8")
    run_date_sequence_download(object(), tmp_path, universe, "2026-08-04", "2026-08-04", 100, 1, 100)
    assert "第 1/3 批" in capsys.readouterr().out
