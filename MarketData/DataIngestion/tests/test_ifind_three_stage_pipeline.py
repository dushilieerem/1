import csv
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.ifind.common.parquet import csv_to_flat_parquet
from data_ingestion.ifind.date_sequence.csv import build_date_sequence_csv, update_date_sequence_csv
from data_ingestion.ifind.date_sequence.download import date_sequence_payload, raw_path as date_raw_path, run_download as run_date_sequence_download
from data_ingestion.ifind.index_weights.csv import build_index_weights_csv, update_index_weights_csv
from data_ingestion.ifind.index_weights.download import index_weights_payload
from data_ingestion.ifind.index_weights.parquet import csv_to_index_weights_parquet
from data_ingestion.ifind.market_data.csv import build_daily_csv, update_daily_csv
from data_ingestion.ifind.market_data.download import LIQUIDITY, PRICE, history_payload, price_group
from data_ingestion.ifind.market_data.parquet import csv_to_parquet


def test_download_payloads_only_describe_iFind_requests():
    assert history_payload(PRICE, ["600000.SH"], "2026-08-04", "2026-08-04")["reqBody"]["functionpara"] == {"CPS": "1"}
    assert history_payload(price_group("qfq"), ["600000.SH"], "2026-08-04", "2026-08-04")["reqBody"]["functionpara"] == {"CPS": "2"}
    assert "functionpara" not in history_payload(price_group("none"), ["600000.SH"], "2026-08-04", "2026-08-04")["reqBody"]
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
    universe = tmp_path / "universe" / "a_share.csv"
    universe.parent.mkdir(parents=True)
    universe.write_text("thscode,exchange\n600000.SH,SH\n", encoding="utf-8")
    assert build_daily_csv(tmp_path, workers=1)["rows"] == 1
    assert build_date_sequence_csv(tmp_path, workers=1)["rows"] == 1
    assert csv_to_parquet(tmp_path / "market_data_hfq.csv", tmp_path / "market_data_hfq.parquet")["rows"] == 1
    with (tmp_path / "market_data_hfq.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0][1] == "600000.SH" and rows[1][1] == "open"
    assert rows[2][rows[1].index("turnover")] == "0.02"
    assert (tmp_path / "market_data_hfq.parquet").is_file()


def test_download_reports_cached_batch_progress(tmp_path, capsys):
    calendar = tmp_path / "calendar" / "calendar_all_a.csv"
    universe = tmp_path / "universe.csv"
    calendar.parent.mkdir(parents=True)
    calendar.write_text("date\n2026-08-04\n", encoding="utf-8")
    universe.write_text("thscode,name\n600000.SH,浦发银行\n000001.SZ,平安银行\n920000.BJ,北交所股票\n", encoding="utf-8")
    for exchange, code in (("SH", "600000.SH"), ("SZ", "000001.SZ"), ("BJ", "920000.BJ")):
        path = date_raw_path(tmp_path, exchange, "2026-08-04", "2026-08-04", 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tables": [], "dataVol": 0}), encoding="utf-8")
    run_date_sequence_download(object(), tmp_path, universe, "2026-08-04", "2026-08-04", 100, 1, 100)
    assert "第 1/3 批" in capsys.readouterr().out


def test_calendar_and_universe_flat_csv_convert_to_parquet(tmp_path):
    calendar = tmp_path / "calendar_all_a.csv"
    universe = tmp_path / "a_share.csv"
    calendar.write_text("date,exchange,is_trade_day\n2026-08-05,ALL_A,true\n", encoding="utf-8")
    universe.write_text("thscode,exchange,name\n600000.SH,SH,浦发银行\n", encoding="utf-8")
    assert csv_to_flat_parquet(calendar, tmp_path / "calendar_all_a.parquet", "test")["rows"] == 1
    assert csv_to_flat_parquet(universe, tmp_path / "a_share.parquet", "test")["columns"] == 3


def test_incremental_csv_update_replaces_only_target_date(tmp_path):
    price = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"open": [10], "high": [11], "low": [9], "close": [10.5]}}]}
    liquidity = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"volume": [100], "amt": [1000], "turn": [2]}}]}
    date_sequence = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"ths_current_mv_stock": [100], "ths_pe_stock": [10], "ths_pb_stock": [1], "ths_the_sw_industry_stock": ["银行"], "ths_the_sw_industry_code_stock": ["801780"], "ths_up_and_down_status_stock": ["正常"]}}]}
    for relative, body in (("prices/hfq/raw/SH/2026-08-04_2026-08-04/symbols_00001.json", price), ("liquidity/raw/SH/2026-08-04_2026-08-04/symbols_00001.json", liquidity), ("date_sequence/raw/SH/2026-08-04_2026-08-04/symbols_00001.json", date_sequence)):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body), encoding="utf-8")
    universe = tmp_path / "universe" / "a_share.csv"
    universe.parent.mkdir(parents=True)
    universe.write_text("thscode,exchange\n600000.SH,SH\n", encoding="utf-8")
    build_daily_csv(tmp_path, workers=1)
    build_date_sequence_csv(tmp_path, workers=1)
    price["tables"][0]["table"]["close"] = [12.0]
    (tmp_path / "prices" / "hfq" / "raw" / "SH" / "2026-08-04_2026-08-04" / "symbols_00001.json").write_text(json.dumps(price), encoding="utf-8")
    assert update_daily_csv(tmp_path, "2026-08-04", workers=1)["replaced_rows"] == 1
    assert update_date_sequence_csv(tmp_path, "2026-08-04", workers=1)["replaced_rows"] == 1
    with (tmp_path / "market_data_hfq.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 3 and rows[2][rows[1].index("close")] == "12.0"
    with (tmp_path / "date_sequence.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 3 and rows[2][rows[1].index("float_mv")] == "100"


def test_index_weights_json_to_csv_and_incremental_update(tmp_path):
    response = {"data": {"columns": ["p03563_f002", "p03563_f004"], "data": [["600000.SH", 0.01], ["000001.SZ", 0.02]]}}
    raw = tmp_path / "index_weights" / "raw" / "000300.SH" / "2026-08-07.json"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    assert index_weights_payload("000300.SH", "2026-08-07") == {"reportname": "p03563", "functionpara": {"date": "20260807", "index_name": "000300.SH"}, "outputpara": "p03563_f002,p03563_f004"}
    assert build_index_weights_csv(tmp_path, "000300.SH")["rows"] == 1
    response["data"]["data"][0][1] = 0.03
    response["data"]["data"].append(["600519.SH", 0.04])
    raw.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    assert update_index_weights_csv(tmp_path, "000300.SH", "2026-08-07")["rows"] == 1
    with (tmp_path / "index_weights" / "000300.SH.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows == [{"date": "2026-08-07", "000001.SZ": "0.02", "600000.SH": "0.03", "600519.SH": "0.04"}]
    result = csv_to_index_weights_parquet(tmp_path / "index_weights" / "000300.SH.csv", tmp_path / "index_weights" / "000300.SH.parquet")
    assert result == {"rows": 1, "columns": 3}
    frame = pd.read_parquet(tmp_path / "index_weights" / "000300.SH.parquet")
    assert frame.index.name == "date" and frame.loc[pd.Timestamp("2026-08-07"), "600000.SH"] == 0.03
