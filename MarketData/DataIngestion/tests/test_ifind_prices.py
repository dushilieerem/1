from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.ifind.prices import (  # noqa: E402
    _download_batch,
    history_payload,
    normalize_history_response,
    price_paths,
)


def _response() -> dict:
    return {
        "tables": [{
            "thscode": "600000.SH",
            "time": ["2026-08-03", "2026-08-04"],
            "table": {
                "open": [10.0, 11.0],
                "high": [11.0, 12.0],
                "low": [9.0, 10.0],
                "close": [10.5, 11.5],
            },
        }],
        "dataVol": 8,
    }


def test_history_payload_uses_confirmed_hfq_protocol():
    assert history_payload(["600000.SH"], "2026-08-04", "2026-08-04") == {
        "reqBody": {
            "codes": "600000.SH",
            "startdate": "2026-08-04",
            "enddate": "2026-08-04",
            "indicators": "open,high,low,close",
            "functionpara": {"CPS": "1"},
        }
    }


def test_normalize_history_response_checks_ohlc_and_emits_long_rows():
    rows = normalize_history_response(_response(), "SH")

    assert rows[0] == {
        "date": "2026-08-03", "thscode": "600000.SH", "exchange": "SH",
        "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5,
        "adjustment": "hfq", "source": "ifind",
    }

    invalid = _response()
    invalid["tables"][0]["table"]["high"][0] = 9.0
    with pytest.raises(ValueError, match="OHLC 关系异常"):
        normalize_history_response(invalid, "SH")


def test_download_batch_saves_raw_response_before_csv_and_replays_it(tmp_path):
    class Client:
        calls = 0

        def post(self, path, payload):
            self.calls += 1
            assert path == "/api/v1/history_data"
            assert payload["reqBody"]["functionpara"] == {"CPS": "1"}
            return _response()

    client = Client()
    assert _download_batch(client, tmp_path, "SH", ["600000.SH"], "2026-08-03", "2026-08-04", 1) == (2, 8, False)
    raw_path, csv_path = price_paths(tmp_path, "SH", "2026-08-03", "2026-08-04", 1)
    assert client.calls == 1
    assert raw_path.is_file()
    assert csv_path.is_file()

    csv_path.unlink()

    class CachedClient:
        def post(self, path, payload):
            raise AssertionError("原始响应存在时不得再次请求 iFinD")

    assert _download_batch(CachedClient(), tmp_path, "SH", ["600000.SH"], "2026-08-03", "2026-08-04", 1) == (2, 8, False)
