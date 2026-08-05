from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.ifind.universe import (  # noqa: E402
    EXPECTED_EXCHANGE_COUNTS,
    INDICATORS,
    download_universe,
    normalize_universe,
    read_codes_from_super_command,
    validate_universe,
)


def _response(codes: list[str]) -> dict:
    names = ["甲", "乙", "丙"]
    exchanges = ["上交所", "深交所", "北交所"]
    boards = ["主板", "创业板", "北交所"]
    return {"tables": [
        {"thscode": code, "table": {
            "ths_stock_short_name_stock": [names[index]],
            "ths_stock_code_stock": [code[:6]],
            "ths_listing_exchange_stock": [exchanges[index]],
            "ths_listed_date_stock": [f"200{index}0101"],
            "ths_listedsector_stock": [boards[index]],
        }}
        for index, code in enumerate(codes)
    ]}


def test_read_codes_from_super_command_ignores_headers(tmp_path):
    command = tmp_path / "command.txt"
    command.write_text(
        'requestHeaders:{"access_token":"secret"}\nformData:{"codes":"600000.SH,000001.SZ"}',
        encoding="utf-8",
    )

    assert read_codes_from_super_command(command) == ["600000.SH", "000001.SZ"]


def test_normalize_universe_maps_vendor_tables_to_security_master_rows():
    rows = normalize_universe(_response(["600000.SH", "000001.SZ", "920000.BJ"]), "2026-08-04")

    assert rows[0] == {
        "symbol": "600000.SH", "thscode": "600000.SH", "code": "600000", "exchange": "SH",
        "listing_exchange": "上交所", "name": "甲", "list_date": "20000101", "board": "主板",
        "security_type": "A_SHARE", "status": "listed", "universe_id": "all_a_5537",
        "as_of_date": "2026-08-04", "source": "ifind",
    }


def test_normalize_universe_rejects_multiple_values_for_one_security():
    response = _response(["600000.SH", "000001.SZ", "920000.BJ"])
    response["tables"][0]["table"]["ths_stock_short_name_stock"] = ["甲", "乙"]

    with pytest.raises(ValueError, match="不是单值"):
        normalize_universe(response, "2026-08-04")


def test_validate_universe_rejects_incomplete_response():
    rows = normalize_universe(_response(["600000.SH", "000001.SZ", "920000.BJ"]), "2026-08-04")

    with pytest.raises(ValueError, match="不一致"):
        validate_universe(rows, ["600000.SH", "000001.SZ"])


def test_download_universe_writes_csv_after_validation(tmp_path):
    unique_codes = [f"{index:06d}.SH" for index in range(EXPECTED_EXCHANGE_COUNTS["SH"])]
    unique_codes += [f"{index:06d}.SZ" for index in range(EXPECTED_EXCHANGE_COUNTS["SZ"])]
    unique_codes += [f"{index:06d}.BJ" for index in range(EXPECTED_EXCHANGE_COUNTS["BJ"])]
    command = tmp_path / "command.txt"
    command.write_text('{"codes":"' + ",".join(unique_codes) + '"}', encoding="utf-8")
    output = tmp_path / "a_share_5537.csv"
    raw_response = tmp_path / "raw_response.json"

    class Client:
        calls = 0

        def post(self, path, payload):
            self.calls += 1
            assert path == "/api/v1/basic_data_service"
            assert [item["indicator"] for item in payload["indipara"]] == list(INDICATORS)
            return {"tables": [
                {"thscode": code, "table": {
                    "ths_stock_short_name_stock": ["名称"],
                    "ths_stock_code_stock": [code[:6]],
                    "ths_listing_exchange_stock": ["交易所"],
                    "ths_listed_date_stock": ["20000101"],
                    "ths_listedsector_stock": ["板块"],
                }}
                for code in unique_codes
            ]}

    client = Client()
    assert download_universe(client, command, output, raw_response, "2026-08-04") == 5537
    assert client.calls == 1
    assert raw_response.is_file()
    assert len(output.read_text(encoding="utf-8-sig").splitlines()) == 5538

    class CachedClient:
        def post(self, path, payload):
            raise AssertionError("存在原始响应时不应再次请求 iFinD")

    assert download_universe(CachedClient(), command, output, raw_response, "2026-08-04") == 5537
