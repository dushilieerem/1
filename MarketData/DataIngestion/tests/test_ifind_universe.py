import csv
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.ifind.universe.pipeline import (  # noqa: E402
    DATA_POOL_FIELDS,
    DELISTING_BLOCK_NAME,
    DELISTED_BLOCK_NAME,
    EXPECTED_EXCHANGE_COUNTS,
    INDICATORS,
    UNIVERSE_COLUMNS,
    build_universe_csv,
    data_pool_payload,
    delisting_raw_path,
    delisted_raw_path,
    default_universe_path,
    download_universe,
    existing_universe_path,
    normalize_data_pool_response,
    normalize_universe,
    read_codes_from_super_command,
    read_universe_columns,
    listed_raw_path,
    run_universe_download,
    snapshot_raw_path,
    update_universe_csv,
    validate_universe,
    write_universe_csv,
)
from data_ingestion.ifind.common.client import IFindClient, IFindRequestError  # noqa: E402


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


def _data_pool_response(codes: list[str]) -> dict:
    return {
        "data": {
            "columns": list(DATA_POOL_FIELDS),
            "data": [[code, f"名称{index}"] for index, code in enumerate(codes)],
        }
    }


def _write_snapshot_raw(root: Path, as_of: str, status: str, codes: list[str]) -> None:
    path = snapshot_raw_path(root, as_of, status)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_data_pool_response(codes), ensure_ascii=False), encoding="utf-8")


def test_read_codes_from_super_command_ignores_headers(tmp_path):
    command = tmp_path / "command.txt"
    command.write_text(
        'requestHeaders:{"access_token":"secret"}\nformData:{"codes":"600000.SH,000001.SZ"}',
        encoding="utf-8",
    )

    assert read_codes_from_super_command(command) == ["600000.SH", "000001.SZ"]


def test_universe_output_uses_variable_name_and_reads_legacy_fallback(tmp_path):
    assert default_universe_path(tmp_path).name == "a_share.csv"
    legacy = tmp_path / "universe" / "a_share_5537.csv"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("thscode\n600000.SH\n", encoding="utf-8")
    assert existing_universe_path(tmp_path) == legacy

    current = default_universe_path(tmp_path)
    current.write_text("thscode\n000001.SZ\n", encoding="utf-8")
    assert existing_universe_path(tmp_path) == current


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


def test_data_pool_payload_matches_listed_and_delisted_protocol():
    assert data_pool_payload("2026-08-10") == {
        "reportname": "p03291",
        "functionpara": {"date": "20260810", "blockname": "001005010", "iv_type": "allcontract"},
        "outputpara": "p03291_f002,p03291_f003",
    }
    assert data_pool_payload("2026-08-10", DELISTED_BLOCK_NAME)["functionpara"]["blockname"] == DELISTED_BLOCK_NAME
    assert data_pool_payload("2026-08-10", DELISTING_BLOCK_NAME)["functionpara"]["blockname"] == DELISTING_BLOCK_NAME


def test_normalize_data_pool_response_uses_code_and_name_fields():
    rows = normalize_data_pool_response(
        _data_pool_response(["600000.SH", "000001.SZ"]),
        "2026-08-10",
        "listed",
        "001005010",
    )

    assert rows[0] == {"thscode": "600000.SH", "name": "名称0"}


def test_only_delisting_snapshot_may_be_empty():
    assert normalize_data_pool_response(
        _data_pool_response([]), "2026-08-10", "delisting", DELISTING_BLOCK_NAME
    ) == []

    for status, blockname in (("listed", "001005010"), ("delisted", DELISTED_BLOCK_NAME)):
        with pytest.raises(ValueError, match="返回空列表"):
            normalize_data_pool_response(_data_pool_response([]), "2026-08-10", status, blockname)


def test_ifind_client_preserves_business_error_response(monkeypatch):
    response = {"errorcode": -4001, "errmsg": "no data.", "dataVol": 0}
    client = IFindClient("refresh-token")
    client._access_token = "access-token"
    monkeypatch.setattr(client, "_post_json", lambda *args, **kwargs: response)

    with pytest.raises(IFindRequestError) as exc_info:
        client.post("/api/v1/data_pool", {})

    assert exc_info.value.errorcode == -4001
    assert exc_info.value.errmsg == "no data."
    assert exc_info.value.response == response


def test_universe_download_fetches_three_cached_snapshots_once(tmp_path):
    class Client:
        calls: list[str] = []

        def post(self, path, payload):
            assert path == "/api/v1/data_pool"
            blockname = payload["functionpara"]["blockname"]
            self.calls.append(blockname)
            assert payload["outputpara"] == "p03291_f002,p03291_f003"
            if blockname == "001005010":
                return _data_pool_response(["600000.SH", "000001.SZ"])
            if blockname == DELISTED_BLOCK_NAME:
                return _data_pool_response(["000003.SZ"])
            return _data_pool_response(["000004.SZ"])

    client = Client()
    first = run_universe_download(client, tmp_path, as_of="2026-08-10")
    assert first["downloaded"] == 3
    assert first["listed"] == 2
    assert first["delisted"] == 1
    assert first["delisting"] == 1
    assert client.calls == ["001005010", DELISTED_BLOCK_NAME, DELISTING_BLOCK_NAME]
    assert listed_raw_path(tmp_path, "2026-08-10").is_file()
    assert delisted_raw_path(tmp_path, "2026-08-10").is_file()
    assert delisting_raw_path(tmp_path, "2026-08-10").is_file()

    class CachedClient:
        def post(self, path, payload):
            raise AssertionError("三类快照均已缓存，不应再次请求 iFinD")

    second = run_universe_download(CachedClient(), tmp_path, as_of="2026-08-10")
    assert second["skipped"] == 3


def test_universe_download_caches_empty_delisting_business_response(tmp_path):
    empty_response = {"errorcode": -4001, "errmsg": "no data.", "dataVol": 0}

    class Client:
        def post(self, path, payload):
            blockname = payload["functionpara"]["blockname"]
            if blockname == "001005010":
                return _data_pool_response(["600000.SH", "000001.SZ"])
            if blockname == DELISTED_BLOCK_NAME:
                return _data_pool_response(["000003.SZ"])
            raise IFindRequestError(
                "iFinD 请求失败（-4001）：no data.",
                errorcode=-4001,
                errmsg="no data.",
                response=empty_response,
            )

    summary = run_universe_download(Client(), tmp_path, as_of="2026-08-10")

    assert summary["delisting"] == 0
    assert json.loads(delisting_raw_path(tmp_path, "2026-08-10").read_text(encoding="utf-8")) == empty_response

    class CachedClient:
        def post(self, path, payload):
            raise AssertionError("空退市整理快照已缓存，不应再次请求 iFinD")

    cached = run_universe_download(CachedClient(), tmp_path, as_of="2026-08-10")
    assert cached["skipped"] == 3
    assert cached["delisting"] == 0


def test_universe_download_does_not_treat_other_empty_pools_as_optional(tmp_path):
    class Client:
        def post(self, path, payload):
            response = {"errorcode": -4001, "errmsg": "no data."}
            raise IFindRequestError(
                "iFinD 请求失败（-4001）：no data.",
                errorcode=-4001,
                errmsg="no data.",
                response=response,
            )

    with pytest.raises(IFindRequestError, match="no data"):
        run_universe_download(Client(), tmp_path, as_of="2026-08-10")


def test_universe_download_rejects_overlap_before_csv_update(tmp_path):
    class Client:
        def post(self, path, payload):
            return _data_pool_response(["000001.SZ"])

    with pytest.raises(ValueError, match="必须互斥"):
        run_universe_download(Client(), tmp_path, as_of="2026-08-10")
    assert not default_universe_path(tmp_path).exists()


def test_build_universe_merges_listed_and_delisted_without_date_matrix(tmp_path):
    _write_snapshot_raw(tmp_path, "2026-08-10", "listed", ["000001.SZ", "600000.SH"])
    _write_snapshot_raw(tmp_path, "2026-08-10", "delisted", ["000003.SZ", "000005.SZ"])
    _write_snapshot_raw(tmp_path, "2026-08-10", "delisting", ["000004.SZ"])

    summary = build_universe_csv(tmp_path)
    output = default_universe_path(tmp_path)
    assert summary == {"rows": 5, "as_of_date": "2026-08-10", "listed": 2, "delisted": 2, "delisting": 1}
    assert read_universe_columns(output) == ["000001.SZ", "000003.SZ", "000004.SZ", "000005.SZ", "600000.SH"]
    assert not (tmp_path / "universe" / "a_share_membership.csv").exists()

    with output.open(encoding="utf-8-sig", newline="") as stream:
        rows = {row["thscode"]: row for row in csv.DictReader(stream)}
    assert rows["000001.SZ"]["name"] == "名称0"
    assert rows["000003.SZ"]["name"] == "名称0"
    assert rows["000004.SZ"]["name"] == "名称0"
    assert rows["000005.SZ"]["name"] == "名称1"
    assert rows["600000.SH"]["name"] == "名称1"


def test_build_universe_rejects_overlap_between_listed_and_delisted(tmp_path):
    _write_snapshot_raw(tmp_path, "2026-08-10", "listed", ["000001.SZ", "600000.SH"])
    _write_snapshot_raw(tmp_path, "2026-08-10", "delisted", ["000003.SZ", "600000.SH"])
    _write_snapshot_raw(tmp_path, "2026-08-10", "delisting", ["000004.SZ"])

    with pytest.raises(ValueError, match="必须互斥"):
        build_universe_csv(tmp_path)
    assert not default_universe_path(tmp_path).exists()


def test_build_universe_rejects_overlap_with_delisting_snapshot(tmp_path):
    _write_snapshot_raw(tmp_path, "2026-08-10", "listed", ["000001.SZ"])
    _write_snapshot_raw(tmp_path, "2026-08-10", "delisted", ["000003.SZ"])
    _write_snapshot_raw(tmp_path, "2026-08-10", "delisting", ["000001.SZ"])

    with pytest.raises(ValueError, match="在市与退市整理快照"):
        build_universe_csv(tmp_path)
    assert not default_universe_path(tmp_path).exists()


def test_update_universe_replaces_the_flat_table_with_the_latest_disjoint_snapshots(tmp_path):
    _write_snapshot_raw(tmp_path, "2026-08-09", "listed", ["000001.SZ"])
    _write_snapshot_raw(tmp_path, "2026-08-09", "delisted", ["000003.SZ"])
    _write_snapshot_raw(tmp_path, "2026-08-09", "delisting", ["000004.SZ"])
    build_universe_csv(tmp_path)

    _write_snapshot_raw(tmp_path, "2026-08-10", "listed", ["000001.SZ", "600000.SH"])
    _write_snapshot_raw(tmp_path, "2026-08-10", "delisted", ["000003.SZ"])
    _write_snapshot_raw(tmp_path, "2026-08-10", "delisting", ["000004.SZ"])
    first = update_universe_csv(tmp_path, "2026-08-10")
    second = update_universe_csv(tmp_path, "2026-08-10")

    assert first["rows"] == 4
    assert first["delisting"] == 1
    assert second["rows"] == 4
    assert first == second


def test_write_universe_csv_preserves_existing_column_order(tmp_path):
    output = tmp_path / "universe" / "a_share.csv"
    row = {column: "" for column in UNIVERSE_COLUMNS}
    row.update({"thscode": "000001.SZ", "name": "名称"})
    write_universe_csv(output, [row])

    assert output.read_text(encoding="utf-8-sig").splitlines()[0].split(",") == list(UNIVERSE_COLUMNS)
