from pathlib import Path
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.ifind.calendar.pipeline import (  # noqa: E402
    backfill_calendar,
    build_calendar_from_existing_sz,
    calendar_path,
    calendar_raw_path,
    default_update_as_of,
    extract_trade_dates,
    fetch_trade_dates,
    read_calendar_dates,
    update_calendar,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


class _Client:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def post(self, path: str, payload: dict) -> dict:
        self.calls.append((path, payload))
        return {"tables": {"tradeDates": ["2021-08-04", "2021/08/05", "20210806"]}}


def test_extract_trade_dates_reads_only_tables_and_normalizes_formats():
    response = {"inputParams": {"startdate": "1900-01-01"}, "tables": {"dates": ["20210806", "2021/08/05", "2021-08-04"]}}

    assert extract_trade_dates(response) == ["2021-08-04", "2021-08-05", "2021-08-06"]


def test_fetch_trade_dates_uses_only_sz_marketcode(tmp_path):
    client = _Client()
    dates = fetch_trade_dates(client, "2021-08-04", "2021-08-06", calendar_raw_path(tmp_path, "2021-08-04", "2021-08-06"))

    assert dates == ["2021-08-04", "2021-08-05", "2021-08-06"]
    assert client.calls[0][1]["marketcode"] == "212100"


def test_default_update_as_of_waits_for_ifind_daily_data():
    before_ready = datetime(2026, 8, 10, 16, 59, tzinfo=SHANGHAI)
    ready = datetime(2026, 8, 10, 17, 0, tzinfo=SHANGHAI)

    assert default_update_as_of(before_ready) == "2026-08-09"
    assert default_update_as_of(ready) == "2026-08-10"


def test_backfill_writes_only_all_a_calendar_and_replays_raw_response(tmp_path):
    client = _Client()
    assert backfill_calendar(client, tmp_path, "2021-08-04", "2021-08-06") == 3
    assert read_calendar_dates(calendar_path(tmp_path)) == ["2021-08-04", "2021-08-05", "2021-08-06"]
    assert not (tmp_path / "calendar" / "SH.csv").exists()

    class CachedClient:
        def post(self, path, payload):
            raise AssertionError("存在原始响应时不应再次请求 iFinD")

    assert backfill_calendar(CachedClient(), tmp_path, "2021-08-04", "2021-08-06") == 0


def test_update_requires_backfill_and_resumes_from_all_a(tmp_path, capsys):
    with pytest.raises(FileNotFoundError, match="统一交易日历"):
        update_calendar(_Client(), tmp_path, "2021-08-10")

    client = _Client()
    backfill_calendar(client, tmp_path, "2021-08-04", "2021-08-06")
    assert update_calendar(client, tmp_path, "2021-08-10") == 0
    assert client.calls[-1][1]["startdate"] == "2021-08-07"
    assert "查询区间：2021-08-07 至 2021-08-10" in capsys.readouterr().out


def test_build_from_existing_sz_creates_full_all_a_calendar(tmp_path):
    source = tmp_path / "calendar" / "SZ.csv"
    source.parent.mkdir(parents=True)
    source.write_text(
        "date,exchange,is_trade_day,source,marketcode\n1990-12-01,SZ,true,ifind,212100\n1995-09-01,SZ,true,ifind,212100\n",
        encoding="utf-8",
    )

    assert build_calendar_from_existing_sz(tmp_path) == 2
    assert read_calendar_dates(calendar_path(tmp_path)) == ["1990-12-01", "1995-09-01"]
