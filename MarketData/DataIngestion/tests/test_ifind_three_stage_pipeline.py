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
from data_ingestion.ifind.index.index_price.csv import build_index_price_csv, update_index_price_csv, update_index_price_csv_range
from data_ingestion.ifind.index.index_price.download import INDEX_PRICE, run_download as run_index_price_download
from data_ingestion.ifind.index.index_price.parquet import csv_to_index_price_parquet
from data_ingestion.ifind.index.index_weights.csv import build_index_weights_csv, update_index_weights_csv, update_index_weights_csv_range
from data_ingestion.ifind.index.index_weights.download import index_weights_payload
from data_ingestion.ifind.index.index_weights.parquet import csv_to_index_weights_parquet
from data_ingestion.ifind.market_data.csv import build_daily_csv, update_daily_csv, update_daily_csv_range
from data_ingestion.ifind.market_data.download import LIQUIDITY, PRICE, history_payload
from data_ingestion.ifind.market_data.parquet import csv_to_parquet
from data_ingestion.ifind.unadjusted_price.csv import build_price_csv, update_price_csv_range
from data_ingestion.ifind.unadjusted_price.download import PRICE as UNADJUSTED_PRICE
from data_ingestion.ifind.unadjusted_price.download import run_download as run_unadjusted_price_download
from data_ingestion.ifind.unadjusted_price.parquet import csv_to_parquet as unadjusted_csv_to_parquet


def test_download_payloads_only_describe_iFind_requests():
    assert history_payload(PRICE, ["600000.SH"], "2026-08-04", "2026-08-04")["reqBody"]["functionpara"] == {"CPS": "1"}
    assert "functionpara" not in history_payload(UNADJUSTED_PRICE, ["600000.SH"], "2026-08-04", "2026-08-04")["reqBody"]
    assert history_payload(LIQUIDITY, ["600000.SH"], "2026-08-04", "2026-08-04")["reqBody"]["indicators"] == "volume,amt,turn"
    index_payload = history_payload(INDEX_PRICE, ["000300.SH"], "2026-08-04", "2026-08-11")
    assert index_payload["reqBody"] == {
        "codes": "000300.SH",
        "startdate": "2026-08-04",
        "enddate": "2026-08-11",
        "indicators": "high,open,low,close",
    }
    assert [item["indicator"] for item in date_sequence_payload(["600000.SH"], "2026-08-04", "2026-08-04")["indipara"]][:3] == ["ths_current_mv_stock", "ths_pe_stock", "ths_pb_stock"]


def test_json_to_complete_csv_to_parquet(tmp_path):
    price = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"open": [10], "high": [11], "low": [9], "close": [10.5]}}]}
    liquidity = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"volume": [100], "amt": [1000], "turn": [2]}}]}
    date_sequence = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"ths_current_mv_stock": [100], "ths_pe_stock": [10], "ths_pb_stock": [1], "ths_the_sw_industry_stock": ["银行"], "ths_the_sw_industry_code_stock": ["801780"], "ths_up_and_down_status_stock": ["正常"]}}]}
    for relative, body in (("market_data/raw/price/SH/2026-08-04_2026-08-04/symbols_00001.json", price), ("market_data/raw/liquidity/SH/2026-08-04_2026-08-04/symbols_00001.json", liquidity), ("date_sequence/raw/SH/2026-08-04_2026-08-04/symbols_00001.json", date_sequence)):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body), encoding="utf-8")
    universe = tmp_path / "universe" / "a_share.csv"
    universe.parent.mkdir(parents=True)
    universe.write_text("thscode,exchange\n600000.SH,SH\n", encoding="utf-8")
    assert build_daily_csv(tmp_path, workers=1)["rows"] == 1
    assert build_date_sequence_csv(tmp_path, workers=1)["rows"] == 1
    assert csv_to_parquet(tmp_path / "market_data" / "market_data_hfq.csv", tmp_path / "market_data" / "market_data_hfq.parquet")["rows"] == 1
    with (tmp_path / "market_data" / "market_data_hfq.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0][1] == "600000.SH" and rows[1][1] == "open"
    assert rows[2][rows[1].index("turnover")] == "0.02"
    assert (tmp_path / "market_data" / "market_data_hfq.parquet").is_file()
    assert not list(tmp_path.glob("*.csv"))
    assert not list(tmp_path.glob("*.parquet"))


def test_unadjusted_price_pipeline_has_only_ohlc(tmp_path):
    price = {"tables": [{"thscode": "600000.SH", "time": ["2026-08-04"], "table": {"open": [10], "high": [11], "low": [9], "close": [10.5]}}]}
    raw = tmp_path / "unadjusted_price" / "raw" / "SH" / "2026-08-04_2026-08-04" / "symbols_00001.json"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps(price), encoding="utf-8")
    universe = tmp_path / "universe" / "a_share.csv"
    universe.parent.mkdir(parents=True)
    universe.write_text("thscode,exchange\n600000.SH,SH\n", encoding="utf-8")

    assert build_price_csv(tmp_path, workers=1)["rows"] == 1
    assert unadjusted_csv_to_parquet(tmp_path / "unadjusted_price" / "unadjusted_price.csv", tmp_path / "unadjusted_price" / "unadjusted_price.parquet")["rows"] == 1
    with (tmp_path / "unadjusted_price" / "unadjusted_price.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[1][1:] == ["open", "high", "low", "close"]
    assert not {"volume", "amount", "turnover"} & set(rows[1])


def test_unadjusted_price_download_never_requests_liquidity(tmp_path):
    class Client:
        def __init__(self):
            self.payloads = []

        def post(self, path, payload):
            self.payloads.append(payload)
            return {"tables": [], "dataVol": 0}

    calendar = tmp_path / "calendar" / "calendar_all_a.csv"
    calendar.parent.mkdir(parents=True)
    calendar.write_text("date\n2026-08-04\n", encoding="utf-8")
    universe = tmp_path / "universe.csv"
    universe.write_text("thscode,name\n600000.SH,浦发银行\n000001.SZ,平安银行\n920000.BJ,北交所股票\n", encoding="utf-8")
    client = Client()

    result = run_unadjusted_price_download(client, tmp_path, universe, "2026-08-04", "2026-08-04", 100, 1, 100)

    assert set(result) == {"price_none"}
    assert len(client.payloads) == 3
    assert all(payload["reqBody"]["indicators"] == "open,high,low,close" for payload in client.payloads)
    assert all("functionpara" not in payload["reqBody"] for payload in client.payloads)


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
    for relative, body in (("market_data/raw/price/SH/2026-08-04_2026-08-04/symbols_00001.json", price), ("market_data/raw/liquidity/SH/2026-08-04_2026-08-04/symbols_00001.json", liquidity), ("date_sequence/raw/SH/2026-08-04_2026-08-04/symbols_00001.json", date_sequence)):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body), encoding="utf-8")
    universe = tmp_path / "universe" / "a_share.csv"
    universe.parent.mkdir(parents=True)
    universe.write_text("thscode,exchange\n600000.SH,SH\n", encoding="utf-8")
    build_daily_csv(tmp_path, workers=1)
    build_date_sequence_csv(tmp_path, workers=1)
    price["tables"][0]["table"]["close"] = [12.0]
    (tmp_path / "market_data" / "raw" / "price" / "SH" / "2026-08-04_2026-08-04" / "symbols_00001.json").write_text(json.dumps(price), encoding="utf-8")
    assert update_daily_csv(tmp_path, "2026-08-04", workers=1)["replaced_rows"] == 1
    assert update_date_sequence_csv(tmp_path, "2026-08-04", workers=1)["replaced_rows"] == 1
    with (tmp_path / "market_data" / "market_data_hfq.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 3 and rows[2][rows[1].index("close")] == "12.0"
    with (tmp_path / "date_sequence" / "date_sequence.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 3 and rows[2][rows[1].index("float_mv")] == "100"


def test_range_csv_updates_merge_all_missing_trade_dates(tmp_path):
    universe = tmp_path / "universe" / "a_share.csv"
    universe.parent.mkdir(parents=True)
    universe.write_text("thscode,exchange\n600000.SH,SH\n", encoding="utf-8")

    for trade_date, close in (("2026-08-08", 10.5), ("2026-08-11", 11.0)):
        price = {
            "tables": [{
                "thscode": "600000.SH",
                "time": [trade_date],
                "table": {"open": [10], "high": [11], "low": [9], "close": [close]},
            }]
        }
        liquidity = {
            "tables": [{
                "thscode": "600000.SH",
                "time": [trade_date],
                "table": {"volume": [100], "amt": [1000], "turn": [2]},
            }]
        }
        for group, body in (("price", price), ("liquidity", liquidity)):
            raw = tmp_path / "market_data" / "raw" / group / "SH" / f"{trade_date}_{trade_date}" / "symbols_00001.json"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(json.dumps(body), encoding="utf-8")
        unadjusted_raw = tmp_path / "unadjusted_price" / "raw" / "SH" / f"{trade_date}_{trade_date}" / "symbols_00001.json"
        unadjusted_raw.parent.mkdir(parents=True, exist_ok=True)
        unadjusted_raw.write_text(json.dumps(price), encoding="utf-8")

    build_daily_csv(tmp_path, workers=1)
    build_price_csv(tmp_path, workers=1)
    result = update_daily_csv_range(
        tmp_path, ["2026-08-08", "2026-08-11"], workers=1
    )
    unadjusted_result = update_price_csv_range(
        tmp_path, ["2026-08-08", "2026-08-11"], workers=1
    )

    assert result["replaced_rows"] == 2
    assert unadjusted_result["replaced_rows"] == 2
    with (tmp_path / "market_data" / "market_data_hfq.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        assert [row[0] for row in list(csv.reader(stream))[2:]] == [
            "2026-08-08",
            "2026-08-11",
        ]


def test_index_range_csv_updates_merge_multiple_dates(tmp_path):
    weights_root = tmp_path / "index" / "index_weights" / "raw" / "000300.SH"
    prices_root = tmp_path / "index" / "index_price" / "raw" / "000300.SH"
    weights_root.mkdir(parents=True)
    prices_root.mkdir(parents=True)
    for trade_date, weight, close in (
        ("2026-08-08", 0.01, 4080),
        ("2026-08-11", 0.02, 4090),
    ):
        (weights_root / f"{trade_date}.json").write_text(
            json.dumps({
                "data": {
                    "columns": ["p03563_f002", "p03563_f004"],
                    "data": [["600000.SH", weight]],
                }
            }),
            encoding="utf-8",
        )
        (prices_root / f"{trade_date}_{trade_date}.json").write_text(
            json.dumps({
                "tables": [{
                    "thscode": "000300.SH",
                    "time": [trade_date],
                    "table": {
                        "high": [4100],
                        "open": [4050],
                        "low": [4000],
                        "close": [close],
                    },
                }]
            }),
            encoding="utf-8",
        )

    build_index_weights_csv(tmp_path, "000300.SH")
    build_index_price_csv(tmp_path, "000300.SH")
    weight_result = update_index_weights_csv_range(
        tmp_path, "000300.SH", ["2026-08-08", "2026-08-11"]
    )
    price_result = update_index_price_csv_range(
        tmp_path, "000300.SH", ["2026-08-08", "2026-08-11"]
    )

    assert weight_result["replaced_rows"] == 2
    assert price_result["replaced_rows"] == 2


def test_index_weights_json_to_csv_and_incremental_update(tmp_path):
    response = {"data": {"columns": ["p03563_f002", "p03563_f004"], "data": [["600000.SH", 0.01], ["000001.SZ", 0.02]]}}
    raw = tmp_path / "index" / "index_weights" / "raw" / "000300.SH" / "2026-08-07.json"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    assert index_weights_payload("000300.SH", "2026-08-07") == {"reportname": "p03563", "functionpara": {"date": "20260807", "index_name": "000300.SH"}, "outputpara": "p03563_f002,p03563_f004"}
    assert build_index_weights_csv(tmp_path, "000300.SH")["rows"] == 1
    response["data"]["data"][0][1] = 0.03
    response["data"]["data"].append(["600519.SH", 0.04])
    raw.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    assert update_index_weights_csv(tmp_path, "000300.SH", "2026-08-07")["rows"] == 1
    with (tmp_path / "index" / "index_weights" / "index_weights_000300.SH.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows == [{"date": "2026-08-07", "000001.SZ": "0.02", "600000.SH": "0.03", "600519.SH": "0.04"}]
    result = csv_to_index_weights_parquet(tmp_path / "index" / "index_weights" / "index_weights_000300.SH.csv", tmp_path / "index" / "index_weights" / "index_weights_000300.SH.parquet")
    assert result == {"rows": 1, "columns": 3}
    frame = pd.read_parquet(tmp_path / "index" / "index_weights" / "index_weights_000300.SH.parquet")
    assert frame.index.name == "date" and frame.loc[pd.Timestamp("2026-08-07"), "600000.SH"] == 0.03


def test_index_price_json_to_csv_and_incremental_update(tmp_path):
    response = {
        "tables": [{
            "thscode": "000300.SH",
            "time": ["2026-08-07"],
            "table": {"high": [4100], "open": [4050], "low": [4000], "close": [4080]},
        }]
    }
    raw = tmp_path / "index" / "index_price" / "raw" / "000300.SH" / "2026-08-07_2026-08-07.json"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps(response), encoding="utf-8")

    assert build_index_price_csv(tmp_path, "000300.SH") == {"rows": 1, "partitions": 1}
    response["tables"][0]["table"]["close"] = [4090]
    raw.write_text(json.dumps(response), encoding="utf-8")
    assert update_index_price_csv(tmp_path, "000300.SH", "2026-08-07")["replaced_rows"] == 1

    csv_path = tmp_path / "index" / "index_price" / "index_price_000300.SH.csv"
    with csv_path.open(encoding="utf-8", newline="") as stream:
        assert list(csv.DictReader(stream)) == [{
            "date": "2026-08-07",
            "open": "4050",
            "high": "4100",
            "low": "4000",
            "close": "4090",
        }]
    parquet_path = tmp_path / "index" / "index_price" / "index_price_000300.SH.parquet"
    assert csv_to_index_price_parquet(csv_path, parquet_path) == {"rows": 1, "columns": 4}
    frame = pd.read_parquet(parquet_path)
    assert frame.index.name == "date" and frame.loc[pd.Timestamp("2026-08-07"), "close"] == 4090


def test_index_price_download_uses_confirmed_history_protocol(tmp_path):
    class Client:
        def __init__(self):
            self.calls = []

        def post(self, path, payload):
            self.calls.append((path, payload))
            return {"tables": [], "dataVol": 0}

    calendar = tmp_path / "calendar" / "calendar_all_a.csv"
    calendar.parent.mkdir(parents=True)
    calendar.write_text("date\n2026-08-04\n2026-08-05\n", encoding="utf-8")
    client = Client()

    result = run_index_price_download(
        client, tmp_path, "000300.SH", "2026-08-04", "2026-08-05", 10, 100
    )

    assert result["raw_partitions"] == 1
    assert client.calls == [(
        "/api/v1/history_data",
        {"reqBody": {
            "codes": "000300.SH",
            "startdate": "2026-08-04",
            "enddate": "2026-08-05",
            "indicators": "high,open,low,close",
        }},
    )]
    assert (tmp_path / "index" / "index_price" / "raw" / "000300.SH" / "2026-08-04_2026-08-05.json").is_file()
